from __future__ import annotations

from fastapi import APIRouter, Depends

from ...config import Settings
from ...schemas import HealthResponse
from ..deps import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)
