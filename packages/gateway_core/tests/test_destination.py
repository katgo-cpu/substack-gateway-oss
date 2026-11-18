from __future__ import annotations

import pytest

from gateway_core import destination
from gateway_core.destination import INVALID_DESTINATION, validate_publication_url


@pytest.fixture(autouse=True)
def _no_allow_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(destination.settings, "allowed_publication_hosts", None)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.substack.com",
        "https://example.substack.com/",
        "HTTPS://Example.Substack.com",
    ],
)
def test_default_accepts_single_label_substack_host(url: str) -> None:
    assert validate_publication_url(url) == "https://example.substack.com"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        " https://example.substack.com",
        "http://example.substack.com",  # not HTTPS
        "ftp://example.substack.com",
        "//example.substack.com",
        "https://example.substack.com:8443",  # port
        "https://user:pw@example.substack.com",  # userinfo
        "https://example.substack.com\\@evil.example",  # parser-confusion trick
        "https://example.substack.com@evil.example",
        "https://example.substack.com/path",
        "https://example.substack.com/?x=1",
        "https://example.substack.com/#frag",
        "https://evil.example",
        "https://substack.com",  # apex is not a publication
        "https://a.b.substack.com",  # more than one label
        "https://example.substack.com.evil.example",
        "https://evil-substack.com",
        "https://127.0.0.1",
        "https://[::1]",
        "https://localhost",
    ],
)
def test_rejects_unsafe_destinations(url: str | None) -> None:
    with pytest.raises(ValueError, match=INVALID_DESTINATION):
        validate_publication_url(url)


def test_error_message_never_echoes_value() -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_publication_url("https://evil.example/secret-token")
    assert "evil.example" not in str(excinfo.value)
    assert "secret-token" not in str(excinfo.value)


def test_allow_list_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        destination.settings, "allowed_publication_hosts", "letter.example.com"
    )
    assert validate_publication_url("https://letter.example.com") == (
        "https://letter.example.com"
    )
    # Once an allow-list exists, even a valid substack.com host is refused.
    with pytest.raises(ValueError):
        validate_publication_url("https://other.substack.com")
    with pytest.raises(ValueError):
        validate_publication_url("https://sub.letter.example.com")


def test_publication_client_validates_destination() -> None:
    from gateway_core.client.publication import PublicationClient

    with pytest.raises(ValueError):
        PublicationClient("sid", "connect", "http://example.substack.com")
    client = PublicationClient("sid", None, "https://example.substack.com/")
    assert client._base == "https://example.substack.com/api/v1"


def test_anonymous_client_may_use_configured_base_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_core.client.publication import PublicationClient

    monkeypatch.setattr(
        destination.settings, "substack_base_url", "https://substack.com"
    )
    anon = PublicationClient("", "", "https://substack.com")
    assert anon._base == "https://substack.com/api/v1"
    # Any session cookie => the apex is not an acceptable publication.
    with pytest.raises(ValueError):
        PublicationClient("sid", None, "https://substack.com")
    # Anonymous does not bypass the check for any other host.
    with pytest.raises(ValueError):
        PublicationClient("", "", "https://evil.example")
