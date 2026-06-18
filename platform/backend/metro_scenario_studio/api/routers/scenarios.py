from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from metro_scenario_studio.api.dependencies import get_scenario_service
from metro_scenario_studio.domain.schemas import (
    CreateScenarioRequest,
    DeriveScenarioRequest,
    UpdateScenarioRequest,
)
from metro_scenario_studio.services.scenario_service import ScenarioService

router = APIRouter(tags=["scenarios"])


@router.post("/api/scenarios", status_code=status.HTTP_201_CREATED)
def create_scenario(request: CreateScenarioRequest, scenario_service: ScenarioService = Depends(get_scenario_service)):
    try:
        return scenario_service.create_scenario(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/scenarios")
def list_scenarios(scenario_service: ScenarioService = Depends(get_scenario_service)):
    return scenario_service.list_executions()


@router.get("/api/scenarios/compare")
def compare_scenarios(
    base_id: str, candidate_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)
):
    try:
        return scenario_service.compare_scenarios(base_id, candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/scenarios/{execution_id}")
def get_scenario(execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)):
    try:
        return scenario_service.get_execution(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/api/scenarios/{execution_id}")
def update_scenario(
    execution_id: str, request: UpdateScenarioRequest, scenario_service: ScenarioService = Depends(get_scenario_service)
):
    try:
        return scenario_service.update_scenario(execution_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/scenarios/{execution_id}/result")
def get_scenario_result(execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)):
    try:
        return scenario_service.get_result(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/scenarios/{execution_id}/audit")
def get_scenario_audit(execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)):
    return scenario_service.get_audit_events(execution_id)


@router.get("/api/scenarios/{execution_id}/artifacts")
def get_scenario_artifacts(execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)):
    return scenario_service.get_excel_artifacts(execution_id)


@router.get("/api/scenarios/{execution_id}/external-snapshot")
def get_scenario_external_snapshot(
    execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)
):
    try:
        return scenario_service.get_external_snapshot(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/scenarios/{execution_id}/run")
def run_scenario(
    execution_id: str,
    scenario_service: ScenarioService = Depends(get_scenario_service),
):
    try:
        return scenario_service.run_scenario(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/scenarios/{execution_id}/explain")
def explain_scenario(
    execution_id: str,
    scenario_service: ScenarioService = Depends(get_scenario_service),
):
    try:
        return scenario_service.explain_scenario(execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/scenarios/{execution_id}/export")
def export_scenario(execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)):
    try:
        path = scenario_service.export_scenario(execution_id)
        return {"path": str(path)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/scenarios/{execution_id}/export/download")
def export_scenario_download(execution_id: str, scenario_service: ScenarioService = Depends(get_scenario_service)):
    try:
        path = scenario_service.export_scenario(execution_id)
        return FileResponse(
            path,
            filename=f"{execution_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/scenarios/{execution_id}/derive", status_code=status.HTTP_201_CREATED)
def derive_scenario(
    execution_id: str, request: DeriveScenarioRequest, scenario_service: ScenarioService = Depends(get_scenario_service)
):
    try:
        return scenario_service.derive_scenario(execution_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
