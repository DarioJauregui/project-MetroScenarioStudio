from __future__ import annotations

from fastapi import Request

from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.services.external_data import ExternalDataService
from metro_scenario_studio.services.nlp_service import NaturalLanguageService
from metro_scenario_studio.services.scenario_service import ScenarioService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_scenario_service(request: Request) -> ScenarioService:
    return request.app.state.scenario_service


def get_external_service(request: Request) -> ExternalDataService:
    return request.app.state.external_service


def get_nlp_service(request: Request) -> NaturalLanguageService:
    return request.app.state.nlp_service
