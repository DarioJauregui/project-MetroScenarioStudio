from __future__ import annotations

import csv
import hashlib
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from metro_scenario_studio.domain.aggregations import aggregate_prediction_rows
from metro_scenario_studio.domain.rules import (
    determine_execution_status,
    determine_real_data_status,
)
from metro_scenario_studio.domain.schemas import (
    AuditEvent,
    CreateScenarioRequest,
    DeriveScenarioRequest,
    ExecutionResult,
    ExplanationItem,
    ImportExcelRequest,
    OriginType,
    ScenarioExecution,
    ScenarioInput,
    ScenarioStatus,
    UpdateScenarioRequest,
)
from metro_scenario_studio.repositories.sqlite_repository import SQLiteRepository
from metro_scenario_studio.services.excel_service import (
    EXCEL_SCHEMA_VERSION,
    export_execution_to_excel,
    import_execution_from_excel,
)
from metro_scenario_studio.services.external_data import ExternalDataService
from metro_scenario_studio.services.prediction_explanation_service import PredictionExplanationService
from metro_scenario_studio.services.prediction_service import PredictionService
from metro_scenario_studio.services.stations import load_station_catalog

if TYPE_CHECKING:
    from metro_scenario_studio.core.config import Settings

logger = logging.getLogger(__name__)


class ScenarioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = SQLiteRepository(settings.sqlite_path)
        self.external_data = ExternalDataService(settings)
        self.prediction = PredictionService(settings)
        self.prediction_explanation = PredictionExplanationService(settings)
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create_scenario(self, request: CreateScenarioRequest) -> ScenarioExecution:
        if request.range_end < request.range_start:
            raise ValueError("range_end must be greater than or equal to range_start")
        initial_slug = "what-if" if request.manual_overrides or request.llm_accepted_items else "base"
        execution = ScenarioExecution(
            id=self._next_execution_id(request.range_start, request.range_end, initial_slug),
            status=ScenarioStatus.DRAFT,
            origin_type=OriginType.MANUAL,
            range_start=request.range_start,
            range_end=request.range_end,
            author=request.author,
            comment=request.comment,
            input=ScenarioInput(
                natural_language_comment=request.natural_language_comment,
                calendar_final=request.calendar_final,
                events_final=request.events_final,
                weather_final=request.weather_final,
                manual_overrides=request.manual_overrides,
                llm_detected_items=request.llm_detected_items,
                llm_accepted_items=request.llm_accepted_items,
                llm_rejected_items=request.llm_rejected_items,
            ),
        )
        self.repository.save_execution(execution)
        return execution

    def update_scenario(self, execution_id: str, request: UpdateScenarioRequest) -> ScenarioExecution:
        execution = self.repository.get_execution(execution_id)
        range_start = request.range_start or execution.range_start
        range_end = request.range_end or execution.range_end
        if range_end < range_start:
            raise ValueError("range_end must be greater than or equal to range_start")

        input_update = execution.input.model_copy(
            update={
                key: value
                for key, value in {
                    "natural_language_comment": request.natural_language_comment,
                    "calendar_final": request.calendar_final,
                    "events_final": request.events_final,
                    "weather_final": request.weather_final,
                    "manual_overrides": request.manual_overrides,
                    "llm_detected_items": request.llm_detected_items,
                    "llm_accepted_items": request.llm_accepted_items,
                    "llm_rejected_items": request.llm_rejected_items,
                }.items()
                if value is not None
            }
        )
        status = execution.status
        origin_type = execution.origin_type
        parent_execution_id = execution.parent_execution_id
        if execution.origin_type == OriginType.EXCEL_IMPORT:
            status = ScenarioStatus.DERIVADA
            origin_type = OriginType.DERIVED
            parent_execution_id = execution.parent_execution_id or execution.id

        updated = execution.model_copy(
            update={
                "range_start": range_start,
                "range_end": range_end,
                "author": request.author if request.author is not None else execution.author,
                "comment": request.comment if request.comment is not None else execution.comment,
                "input": input_update,
                "status": status,
                "origin_type": origin_type,
                "parent_execution_id": parent_execution_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.repository.save_execution(updated)
        return updated

    def run_scenario(self, execution_id: str) -> ExecutionResult:
        execution = self.repository.get_execution(execution_id)
        snapshot = self.external_data.get_snapshot(execution.range_start, execution.range_end)
        execution.input.calendar_final = execution.input.calendar_final or snapshot.calendar
        execution.input.events_final = execution.input.events_final or snapshot.events
        execution.input.weather_final = execution.input.weather_final or snapshot.weather

        has_manual_changes = (
            bool(execution.input.manual_overrides)
            or any(item.modified for item in execution.input.calendar_final)
            or any(item.modified for item in execution.input.events_final)
            or any(item.modified for item in execution.input.weather_final)
        )
        has_accepted_llm = bool(execution.input.llm_accepted_items)
        status = determine_execution_status(
            origin_type=execution.origin_type,
            has_manual_changes=has_manual_changes,
            has_accepted_llm_items=has_accepted_llm,
            imported_modified=False,
        )
        has_forecastable_context = bool(execution.input.events_final) or bool(execution.input.weather_final)
        model_variant = (
            "forecastable_scenario"
            if status in {ScenarioStatus.WHAT_IF, ScenarioStatus.DERIVADA} or has_forecastable_context
            else "strict_available"
        )
        execution = execution.model_copy(
            update={
                "status": status,
                "model_variant": model_variant,
                "warnings": [warning.code for warning in snapshot.warnings],
                "updated_at": datetime.now(UTC),
                "executed_at": datetime.now(UTC),
            }
        )
        rows = self.prediction.predict(execution)
        prediction_warnings = [
            *self.prediction.diagnostics(),
            *self._prediction_warnings(execution, rows),
        ]
        if self._is_complete_historical_evaluation(execution, rows):
            if status == ScenarioStatus.BASE:
                status = ScenarioStatus.HISTORICO_EVALUADO
            prediction_warnings.append("historical_evaluation_leakage_risk")
        execution = execution.model_copy(
            update={
                "status": status,
                "real_data_status": determine_real_data_status(rows),
                "warnings": [*execution.warnings, *prediction_warnings],
            }
        )
        aggregates = aggregate_prediction_rows(rows)

        csv_demand = self._load_historical_network_demand()

        # Update aggregates with CSV actuals
        for agg in aggregates:
            if agg.level == "network_date" and agg.target_date in csv_demand:
                agg.y_real = csv_demand[agg.target_date]
                agg.real_available = True
                agg.abs_error = round(abs(agg.y_pred - agg.y_real), 6)
                agg.pct_error = round(agg.abs_error / agg.y_real, 12) if agg.y_real != 0 else None

        # Re-aggregate overall network total if daily totals were updated
        network_agg = next((agg for agg in aggregates if agg.level == "network"), None)
        if network_agg:
            network_dates = [agg for agg in aggregates if agg.level == "network_date"]
            real_values = [agg.y_real for agg in network_dates if agg.y_real is not None]
            network_agg.y_real = round(sum(real_values), 6) if real_values else None
            network_agg.real_available = network_agg.y_real is not None
            if network_agg.y_real is not None:
                network_agg.abs_error = round(abs(network_agg.y_pred - network_agg.y_real), 6)
                network_agg.pct_error = (
                    round(network_agg.abs_error / network_agg.y_real, 12) if network_agg.y_real != 0 else None
                )

        if any(row.real_available for row in rows) or any(agg.real_available for agg in aggregates):
            execution = execution.model_copy(update={"real_data_status": "datos reales disponibles"})

        explanations = self._build_explanations(
            execution,
            snapshot_warnings=[warning.message for warning in snapshot.warnings],
        )
        audit_events = [
            AuditEvent(
                execution_id=execution.id,
                actor=execution.author,
                action="run_prediction",
                summary="Prediction executed from explicit user action.",
                payload={"status": execution.status.value, "model_variant": execution.model_variant},
            )
        ]
        result = ExecutionResult(
            execution=execution,
            prediction_rows=rows,
            aggregates=aggregates,
            explanations=explanations,
            audit_events=audit_events,
            narrative_summary="__GENERATING__" if self.settings.explanation_llm_enabled else None,
        )
        self.repository.save_external_snapshot(execution_id=execution.id, snapshot=snapshot)
        self.repository.save_result(result)
        return result

    def _load_historical_network_demand(self) -> dict[object, float]:
        csv_path = self.settings.historical_demand_csv
        csv_demand = {}
        if csv_path is None or not csv_path.exists():
            return csv_demand
        try:
            with csv_path.open(encoding="utf-8-sig", newline="") as file_handle:
                reader = csv.DictReader(file_handle)
                for row in reader:
                    fecha_str = row.get("Fecha") or row.get("\ufeffFecha")
                    viajeros_str = row.get("Viajeros")
                    if not fecha_str or not viajeros_str:
                        continue
                    try:
                        fecha = datetime.strptime(fecha_str.strip(), "%Y-%m-%d").date()
                        csv_demand[fecha] = float(viajeros_str.strip())
                    except ValueError:
                        continue
        except OSError as exc:
            logger.warning("Error reading historical demand CSV at %s: %s", csv_path, exc)
        return csv_demand

    def explain_scenario(self, execution_id: str) -> ExecutionResult:
        result = self.repository.get_result(execution_id)
        if self.settings.explanation_llm_enabled:
            try:
                summary = self.prediction_explanation.summarize(result)
                result_updated = result.model_copy(update={"narrative_summary": summary})
                self.repository.save_result(result_updated)
                return result_updated
            except Exception as exc:
                logger.exception("Failed to generate async explanation: %s", exc)
                result_updated = result.model_copy(
                    update={"narrative_summary": "Error al generar la explicación narrativa con IA."}
                )
                self.repository.save_result(result_updated)
                return result_updated
        else:
            result_updated = result.model_copy(update={"narrative_summary": None})
            self.repository.save_result(result_updated)
            return result_updated

    def _prediction_warnings(self, execution: ScenarioExecution, rows) -> list[str]:
        if not rows:
            return ["model_predictions_unavailable"]
        warnings: list[str] = []
        expected_dates = {
            execution.range_start + timedelta(days=offset)
            for offset in range((execution.range_end - execution.range_start).days + 1)
        }
        predicted_dates = {row.target_date for row in rows}
        if predicted_dates != expected_dates:
            warnings.append("model_prediction_partial")
        expected_series_count = len(load_station_catalog(self.settings.metro_demand_models_root))
        if expected_series_count:
            for target_date in predicted_dates:
                series_count = len({row.series_id for row in rows if row.target_date == target_date})
                if series_count < expected_series_count:
                    warnings.append("model_series_partial")
                    break
        return warnings

    def _is_complete_historical_evaluation(self, execution: ScenarioExecution, rows) -> bool:
        if execution.origin_type != OriginType.MANUAL or not rows:
            return False
        expected_dates = {
            execution.range_start + timedelta(days=offset)
            for offset in range((execution.range_end - execution.range_start).days + 1)
        }
        rows_with_real = [row for row in rows if row.y_real is not None]
        dates_with_real = {row.target_date for row in rows_with_real}
        return bool(expected_dates) and expected_dates.issubset(dates_with_real)

    def export_scenario(self, execution_id: str) -> Path:
        result = self.repository.get_result(execution_id)
        output_dir = self.settings.artifacts_dir / execution_id
        output_path = output_dir / f"{execution_id}.xlsx"
        export_execution_to_excel(result.execution, result, output_path)
        checksum = _file_checksum(output_path)
        self.repository.save_excel_artifact(
            execution_id=execution_id,
            artifact_type="export",
            path=output_path,
            checksum=checksum,
            schema_version=EXCEL_SCHEMA_VERSION,
        )
        self.repository.add_audit_event(
            AuditEvent(
                execution_id=execution_id,
                actor=result.execution.author,
                action="export_excel",
                summary="Excel artifact exported for the execution.",
                payload={"path": str(output_path), "checksum": checksum},
            )
        )
        return output_path

    def import_scenario(self, request: ImportExcelRequest) -> ExecutionResult:
        execution, result = import_execution_from_excel(Path(request.path))
        self.repository.save_result(result)
        self.repository.save_excel_artifact(
            execution_id=execution.id,
            artifact_type="import",
            path=Path(request.path),
            checksum=_file_checksum(Path(request.path)),
            schema_version=EXCEL_SCHEMA_VERSION,
        )
        return result

    def import_uploaded_scenario(self, source_file, filename: str) -> ExecutionResult:
        imports_dir = self.settings.artifacts_dir / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name or "scenario.xlsx"
        target_path = imports_dir / f"{uuid4().hex[:12]}_{safe_name}"
        with target_path.open("wb") as file_handle:
            shutil.copyfileobj(source_file, file_handle)
        execution, result = import_execution_from_excel(target_path)
        self.repository.save_result(result)
        self.repository.save_excel_artifact(
            execution_id=execution.id,
            artifact_type="import_upload",
            path=target_path,
            checksum=_file_checksum(target_path),
            schema_version=EXCEL_SCHEMA_VERSION,
        )
        return result

    def derive_scenario(self, execution_id: str, request: DeriveScenarioRequest) -> ScenarioExecution:
        source = self.repository.get_execution(execution_id)
        derived = source.model_copy(
            update={
                "id": f"scn_{uuid4().hex[:12]}",
                "status": ScenarioStatus.DERIVADA,
                "origin_type": OriginType.DERIVED,
                "parent_execution_id": source.id,
                "comment": request.comment or source.comment,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "executed_at": None,
            }
        )
        self.repository.save_execution(derived)
        return derived

    def get_execution(self, execution_id: str) -> ScenarioExecution:
        return self.repository.get_execution(execution_id)

    def get_result(self, execution_id: str) -> ExecutionResult:
        return self.repository.get_result(execution_id)

    def get_audit_events(self, execution_id: str) -> list[AuditEvent]:
        return self.repository.get_audit_events(execution_id)

    def get_excel_artifacts(self, execution_id: str) -> list[dict[str, object]]:
        return self.repository.get_excel_artifacts(execution_id)

    def get_external_snapshot(self, execution_id: str):
        return self.repository.get_external_snapshot(execution_id)

    def list_executions(self) -> list[ScenarioExecution]:
        return self.repository.list_executions()

    def metrics(self) -> dict[str, object]:
        return self.prediction.model_registry_snapshot()

    def _next_execution_id(self, range_start, range_end, status_slug: str) -> str:
        prefix = f"scn_{range_start:%Y%m%d}-{range_end:%Y%m%d}_{status_slug}_"
        for index in range(1, 1000):
            candidate = f"{prefix}{index:03d}"
            if not self.repository.execution_exists(candidate):
                return candidate
        return f"{prefix}{uuid4().hex[:6]}"

    def compare_scenarios(self, base_id: str, candidate_id: str) -> dict[str, object]:
        base = self.repository.get_result(base_id)
        candidate = self.repository.get_result(candidate_id)
        candidate_by_key = {_aggregate_key(row): row for row in candidate.aggregates}
        rows: list[dict[str, object]] = []
        for base_row in base.aggregates:
            candidate_row = candidate_by_key.get(_aggregate_key(base_row))
            if candidate_row is None:
                continue
            delta_abs = round(candidate_row.y_pred - base_row.y_pred, 6)
            delta_pct = round(delta_abs / base_row.y_pred, 12) if base_row.y_pred else None
            rows.append(
                {
                    "level": base_row.level,
                    "target_date": base_row.target_date.isoformat() if base_row.target_date else None,
                    "linea": base_row.linea,
                    "estacion": base_row.estacion,
                    "base_y_pred": base_row.y_pred,
                    "candidate_y_pred": candidate_row.y_pred,
                    "delta_abs": delta_abs,
                    "delta_pct": delta_pct,
                }
            )
        return {
            "base_execution_id": base_id,
            "candidate_execution_id": candidate_id,
            "rows": rows,
            "notes": [
                "Escenario comparado por suma desde agregados derivados de fecha-linea-estacion.",
                "Las diferencias what-if son simulaciones asociadas al modelo; no deben interpretarse como causalidad.",
            ],
        }

    def _build_explanations(
        self,
        execution: ScenarioExecution,
        *,
        snapshot_warnings: list[str],
    ) -> list[ExplanationItem]:
        items = [
            ExplanationItem(
                section="resumen",
                item_type="execution",
                label="Ejecucion manual",
                description="La prediccion se lanzo mediante boton y quedo registrada con snapshot completo.",
                source="system",
                used_by_model=True,
                confidence="high",
                limitation=None,
            ),
            ExplanationItem(
                section="variables_usadas",
                item_type="model_variant",
                label=execution.model_variant,
                description="Variante del modelo usada en esta ejecucion.",
                source="model_registry",
                used_by_model=True,
                confidence="high",
                limitation="Los factores se interpretan como asociaciones del modelo, no causalidad.",
            ),
        ]
        if execution.input.manual_overrides:
            items.append(
                ExplanationItem(
                    section="variables_modificadas",
                    item_type="manual_override",
                    label="Cambios manuales",
                    description="El usuario introdujo cambios manuales; la ejecucion se trata como escenario what-if o derivado.",
                    source="user",
                    used_by_model=execution.model_variant == "forecastable_scenario",
                    confidence="medium",
                    limitation="Un cambio registrado puede no entrar en la variante strict_available.",
                )
            )
        if execution.input.llm_accepted_items:
            items.append(
                ExplanationItem(
                    section="texto_libre",
                    item_type="llm_validated",
                    label="Elementos aceptados desde comentario",
                    description="El comentario natural aporto variables estructuradas aceptadas por validacion humana.",
                    source="llm_with_human_validation",
                    used_by_model=execution.model_variant == "forecastable_scenario",
                    confidence="medium",
                    limitation="El LLM no ejecuta ni aplica cambios sin validacion humana.",
                )
            )
        for warning in snapshot_warnings:
            items.append(
                ExplanationItem(
                    section="limitaciones",
                    item_type="warning",
                    label="Aviso de cobertura",
                    description=warning,
                    source="coverage_rules",
                    used_by_model=False,
                    confidence="high",
                    limitation=warning,
                )
            )
        return items


def _file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aggregate_key(row) -> tuple[object, ...]:
    return (row.level, row.target_date, row.linea, row.estacion)
