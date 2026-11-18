from __future__ import annotations

from gateway_core.client.base import SubstackHTTPBase
from gateway_core.destination import resolve_publication_destination

_API_PREFIX = "api/v1"


class PublicationClient(SubstackHTTPBase):
    """HTTP client scoped to a single Substack publication.

    Handles all requests to ``{publication_url}/api/v1/*``.
    Domain logic lives in the service classes (``gateway_core.services.*``).
    """

    def __init__(
        self,
        substack_sid: str,
        connect_sid: str | None,
        publication_url: str,
        request_id: str | None = None,
    ) -> None:
        super().__init__(substack_sid, connect_sid, request_id)
        destination = resolve_publication_destination(
            publication_url, has_session=bool(substack_sid or connect_sid)
        )
        self._base = f"{destination}/{_API_PREFIX}"
