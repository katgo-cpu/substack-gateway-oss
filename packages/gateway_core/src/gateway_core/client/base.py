from __future__ import annotations

import logging
import time
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from gateway_core.client.exceptions import SubstackAPIError, SubstackAuthError
from gateway_core.client.transport import (
    default_transport_factory,
    get_transport_factory,
)
from gateway_core.config import settings

_log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(
    timeout=settings.substack_timeout_sec,
    connect=settings.substack_connect_timeout_sec,
)


def _build_limits() -> httpx.Limits:
    return httpx.Limits(
        max_connections=settings.substack_max_connections,
        max_keepalive_connections=settings.substack_max_keepalive_connections,
    )


_LIMITS = _build_limits()


def _safe_url(url: str) -> str:
    """host + path only: no query string, userinfo or fragment in logs."""
    parts = urlsplit(url)
    return f"{parts.hostname}{parts.path}"


def _get_limits() -> httpx.Limits:
    global _LIMITS
    if (
        _LIMITS.max_connections != settings.substack_max_connections
        or _LIMITS.max_keepalive_connections
        != settings.substack_max_keepalive_connections
    ):
        _LIMITS = _build_limits()
    return _LIMITS


class SubstackHTTPBase:
    """Raw HTTP layer shared by PublicationClient and SubstackClient."""

    _base: str  # set by each concrete subclass

    def __init__(
        self,
        substack_sid: str,
        connect_sid: str | None,
        request_id: str | None = None,
    ) -> None:
        self._cookies = {"substack.sid": substack_sid}
        if connect_sid:
            self._cookies["connect.sid"] = connect_sid
        self._http: httpx.AsyncClient | None = None
        self._rid = f"[{request_id}] " if request_id else ""

    async def __aenter__(self) -> Self:
        factory = get_transport_factory()
        if factory is default_transport_factory:
            # Stock path: let httpx build its own transport so environment
            # proxies (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY) keep working.
            self._http = httpx.AsyncClient(
                cookies=self._cookies,
                timeout=_TIMEOUT,
                limits=_get_limits(),
                follow_redirects=False,
            )
        else:
            # Limits go to the transport because httpx ignores `limits=` when a
            # transport is given.
            self._http = httpx.AsyncClient(
                cookies=self._cookies,
                timeout=_TIMEOUT,
                transport=factory(_get_limits()),
                follow_redirects=False,
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", self._url(path), **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", self._url(path), **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("PUT", self._url(path), **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._request("DELETE", self._url(path), **kwargs)

    async def _send_request(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        if self._http is None:
            raise RuntimeError("Client must be used as an async context manager")

        start = time.monotonic()
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            elapsed = time.monotonic() - start
            # Exception class only: str(exc) can embed URLs, proxies or headers.
            _log.warning(
                "%sSubstack network error: %s %s — %s (%.3fs)",
                self._rid,
                method,
                _safe_url(url),
                type(exc).__name__,
                elapsed,
            )
            raise SubstackAPIError(502, "Network error contacting Substack") from exc

        elapsed = time.monotonic() - start
        if response.is_redirect:
            # Never follow or echo a redirect: it could carry the session
            # cookies to another host. The Location value is deliberately
            # not logged or returned.
            _log.warning(
                "%s← %s %s → %d redirect refused (%.3fs)",
                self._rid,
                method,
                _safe_url(url),
                response.status_code,
                elapsed,
            )
            raise SubstackAPIError(502, "Substack returned an unexpected redirect")
        if response.status_code == 401:
            _log.warning(
                "%s← %s %s → 401 Unauthorized (%.3fs)",
                self._rid,
                method,
                _safe_url(url),
                elapsed,
            )
            raise SubstackAuthError(401, "Invalid or expired Substack session token")
        if response.status_code == 403:
            _log.warning(
                "%s← %s %s → 403 Forbidden (%.3fs)",
                self._rid,
                method,
                _safe_url(url),
                elapsed,
            )
            raise SubstackAuthError(
                403, "Forbidden: insufficient permissions for this resource"
            )
        if not response.is_success:
            self._raise_api_error(method, url, response, elapsed)
        _log.debug(
            "%s← %s %s → %d (%.3fs)",
            self._rid,
            method,
            _safe_url(url),
            response.status_code,
            elapsed,
        )
        return response

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return await self._send_request(method, url, **kwargs)

    def _raise_api_error(
        self, method: str, url: str, response: httpx.Response, elapsed: float
    ) -> None:
        # The upstream body is intentionally never read, logged or returned:
        # it can contain account details, tokens or internal diagnostics.
        _log.warning(
            "%s← %s %s → %d (%.3fs)",
            self._rid,
            method,
            _safe_url(url),
            response.status_code,
            elapsed,
        )
        raise SubstackAPIError(
            response.status_code,
            f"Substack returned HTTP {response.status_code}",
        )
