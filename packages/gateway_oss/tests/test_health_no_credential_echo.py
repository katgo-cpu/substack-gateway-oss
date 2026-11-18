from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway_oss.api.deps import get_substack_client
from gateway_oss.api.v1.health import router
from gateway_oss.models.schemas import HealthResponse

_SECRET_SID = "s%3Asuper-secret-session"


class _FakeClient:
    async def check_connectivity(self) -> bool:
        return True


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def _fake() -> _FakeClient:
        return _FakeClient()

    app.dependency_overrides[get_substack_client] = _fake
    return app


def _token() -> str:
    payload = {
        "publication_url": "https://example.substack.com",
        "substack_sid": _SECRET_SID,
        "connect_sid": _SECRET_SID,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.parametrize("query", ["", "?show=true", "?show=1&tokens=true"])
def test_ready_never_returns_credentials(query: str) -> None:
    client = TestClient(_app())
    response = client.get(
        f"/health/ready{query}", headers={"x-gateway-token": _token()}
    )
    assert response.status_code == 200
    assert response.json() == {"connected": True}
    assert _SECRET_SID not in response.text
    assert "tokens" not in response.json()


def test_health_response_has_no_token_field() -> None:
    assert set(HealthResponse.model_fields) == {"connected"}
