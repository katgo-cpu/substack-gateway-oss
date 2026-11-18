"""Strict validation of the publication host that session cookies are sent to.

The publication URL arrives inside a caller-supplied token. Without a check, a
wrong or hostile value would make the gateway send the Substack session
cookies to an arbitrary host (or over plain HTTP). Everything here fails
closed and never echoes the offending value back to the caller.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from gateway_core.config import settings

# One DNS label directly under substack.com, e.g. "example.substack.com".
_SUBSTACK_LABEL_HOST = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.substack\.com$"
)
_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

INVALID_DESTINATION = "publication_url is not an allowed HTTPS publication host"


def allowed_publication_hosts() -> frozenset[str]:
    """Exact hosts from ``SUBSTACK_GATEWAY_ALLOWED_PUBLICATION_HOSTS`` (comma list)."""
    raw = settings.allowed_publication_hosts or ""
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def validate_publication_url(url: str | None) -> str:
    """Return the normalised ``https://host`` origin or raise ``ValueError``.

    Rules (all must hold):
    * scheme is exactly ``https``;
    * no userinfo, port, query or fragment, and no path beyond ``/``;
    * hostname is a plain lowercase ASCII DNS name (no IP literals);
    * when an allow-list is configured the host must be in it exactly;
      otherwise it must be a single label directly under ``substack.com``.
    """
    if not url or not isinstance(url, str) or url != url.strip():
        raise ValueError(INVALID_DESTINATION)
    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError for a malformed port
    except ValueError as exc:
        raise ValueError(INVALID_DESTINATION) from exc
    host = parts.hostname
    if (
        parts.scheme != "https"
        or host is None
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
        or not _HOST.match(host)
    ):
        raise ValueError(INVALID_DESTINATION)
    allowed = allowed_publication_hosts()
    if allowed:
        if host not in allowed:
            raise ValueError(INVALID_DESTINATION)
    elif not _SUBSTACK_LABEL_HOST.match(host):
        raise ValueError(INVALID_DESTINATION)
    return f"https://{host}"


def resolve_publication_destination(url: str | None, *, has_session: bool) -> str:
    """Destination for a PublicationClient.

    A client carrying no session cookie (anonymous public reads) may target the
    operator-configured Substack base URL exactly, because nothing sensitive is
    sent. Any client that carries a session cookie, and any other URL, must
    pass :func:`validate_publication_url`.
    """
    base = settings.substack_base_url.rstrip("/")
    if not has_session and isinstance(url, str) and url.rstrip("/") == base:
        return base
    return validate_publication_url(url)
