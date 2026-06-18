from __future__ import annotations

from fastapi import APIRouter, Depends

from metro_scenario_studio.api.dependencies import get_settings
from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.services.stations import load_station_catalog

router = APIRouter(tags=["stations"])


@router.get("/api/stations")
def station_catalog(settings: Settings = Depends(get_settings)):
    return load_station_catalog(settings.metro_demand_models_root)
