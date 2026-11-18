from __future__ import annotations

import base64
import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gateway_rest_common.deps import get_credentials

_SECRET = "s%3Atop-secret-session-value"


def _client() -> TestClient:
    app = FastAPI()

    # Exercise the real token-validation dependency used by every route.
    @app.get("/probe")
    def probe(_: object = Depends(get_credentials)) -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def _b64(payload: object) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


_CASES = [
    ("not-base64!!", "expected base64-encoded JSON credentials"),
    (base64.b64encode(b"not json").decode(), "expected base64-encoded JSON"),
    (
        _b64({"publication_url": "https://example.substack.com", "substack_sid": ""}),
        "must contain substack_sid",
    ),
    (_b64({"substack_sid": _SECRET}), "must contain publication_url"),
    (
        _b64(
            {"publication_url": "http://example.substack.com", "substack_sid": _SECRET}
        ),
        "not an allowed HTTPS publication host",
    ),
]


@pytest.mark.parametrize(("token", "reason"), _CASES)
def test_rejection_logs_specific_reason_without_leaking(
    token: str, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="gateway_rest_common.deps"):
        response = _client().get("/probe", headers={"x-gateway-token": token})
    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid credentials"
    }  # caller sees nothing new
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert reason in messages
    assert _SECRET not in messages
    assert token not in messages


def test_valid_token_is_accepted() -> None:
    token = _b64(
        {"publication_url": "https://example.substack.com", "substack_sid": _SECRET}
    )
    response = _client().get("/probe", headers={"x-gateway-token": token})
    assert response.status_code == 200
