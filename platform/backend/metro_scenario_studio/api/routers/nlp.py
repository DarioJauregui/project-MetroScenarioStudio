from __future__ import annotations

from fastapi import APIRouter, Depends

from metro_scenario_studio.api.dependencies import get_nlp_service, get_settings
from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.domain.schemas import NlpParseRequest
from metro_scenario_studio.services.nlp_service import NaturalLanguageService
from metro_scenario_studio.services.stations import load_station_catalog

router = APIRouter(tags=["nlp"])


@router.post("/api/nlp/parse")
def parse_natural_language(
    request: NlpParseRequest,
    settings: Settings = Depends(get_settings),
    nlp_service: NaturalLanguageService = Depends(get_nlp_service),
):
    station_rows = load_station_catalog(settings.metro_demand_models_root)
    return nlp_service.parse(
        request.comment,
        reference_date=request.range_start,
        stations=[item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in station_rows],
        require_explicit_temporal_hint=True,
    )
