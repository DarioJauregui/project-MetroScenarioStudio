from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from metro_scenario_studio.api.routers.external_data import router as external_data_router
from metro_scenario_studio.api.routers.health import router as health_router
from metro_scenario_studio.api.routers.imports import router as imports_router
from metro_scenario_studio.api.routers.metrics import router as metrics_router
from metro_scenario_studio.api.routers.nlp import router as nlp_router
from metro_scenario_studio.api.routers.scenarios import router as scenarios_router
from metro_scenario_studio.api.routers.stations import router as stations_router
from metro_scenario_studio.core.config import Settings, get_settings
from metro_scenario_studio.services.external_data import ExternalDataService
from metro_scenario_studio.services.nlp_service import NaturalLanguageService
from metro_scenario_studio.services.scenario_service import ScenarioService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scenario_service = ScenarioService(resolved_settings)
    external_service = ExternalDataService(resolved_settings)
    nlp_service = NaturalLanguageService(resolved_settings)

    app = FastAPI(title=resolved_settings.app_name, version="0.1.0")

    # Store references in state for dependency injection
    app.state.settings = resolved_settings
    app.state.scenario_service = scenario_service
    app.state.external_service = external_service
    app.state.nlp_service = nlp_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request/Response logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start_time
        logger.info(
            f"Method: {request.method} Path: {request.url.path} "
            f"Status: {response.status_code} Duration: {duration:.4f}s"
        )
        return response

    # Include routers
    app.include_router(health_router)
    app.include_router(scenarios_router)
    app.include_router(imports_router)
    app.include_router(nlp_router)
    app.include_router(metrics_router)
    app.include_router(stations_router)
    app.include_router(external_data_router)

    return app


app = create_app()
