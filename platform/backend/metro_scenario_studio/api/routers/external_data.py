from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from metro_scenario_studio.api.dependencies import get_external_service
from metro_scenario_studio.services.external_data import ExternalDataService

router = APIRouter(tags=["external-data"])


@router.get("/api/external-data")
def external_data(start: date, end: date, external_service: ExternalDataService = Depends(get_external_service)):
    try:
        return external_service.get_snapshot(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
