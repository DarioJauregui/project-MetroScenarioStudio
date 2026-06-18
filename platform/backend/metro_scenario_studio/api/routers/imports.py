from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from metro_scenario_studio.api.dependencies import get_scenario_service
from metro_scenario_studio.domain.schemas import ImportExcelRequest
from metro_scenario_studio.services.scenario_service import ScenarioService

router = APIRouter(tags=["imports"])


@router.post("/api/imports", status_code=status.HTTP_201_CREATED)
def import_scenario(request: ImportExcelRequest, scenario_service: ScenarioService = Depends(get_scenario_service)):
    try:
        return scenario_service.import_scenario(request)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/imports/upload", status_code=status.HTTP_201_CREATED)
def upload_import(file: UploadFile = File(...), scenario_service: ScenarioService = Depends(get_scenario_service)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")
    try:
        return scenario_service.import_uploaded_scenario(file.file, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
