from __future__ import annotations

from fastapi import APIRouter, Depends

from metro_scenario_studio.api.dependencies import get_settings
from metro_scenario_studio.core.config import Settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "explanation_llm_enabled": settings.explanation_llm_enabled,
        "explanation_llm_endpoint": settings.explanation_llm_endpoint,
        "explanation_llm_model": settings.explanation_llm_model,
    }
