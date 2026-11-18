from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gateway_oss.api.deps import get_substack_client
from gateway_oss.client.substack import SubstackClient
from gateway_oss.models.schemas import (
    HealthResponse,
    LivenessResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LivenessResponse)
async def health_live() -> LivenessResponse:
    """Public liveness probe — no auth required."""
    return LivenessResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def health_ready(
    client: Annotated[SubstackClient, Depends(get_substack_client)],
) -> HealthResponse:
    """Authenticated readiness probe — verifies Substack connectivity.

    Returns only ``connected``. It never returns credentials (an earlier
    ``?show=true`` option echoed the full token and has been removed; an
    unknown ``show`` query parameter is simply ignored). Connectivity is NOT
    proof of identity or publication permission.
    """
    return HealthResponse(connected=await client.check_connectivity())
