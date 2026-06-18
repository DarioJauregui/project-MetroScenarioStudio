from __future__ import annotations

from typing import TYPE_CHECKING

from metro_scenario_studio.domain.schemas import (
    CoverageSummary,
    OriginType,
    PredictionRow,
    ScenarioStatus,
    WarningItem,
)

if TYPE_CHECKING:
    from datetime import date


def determine_execution_status(
    *,
    origin_type: OriginType,
    has_manual_changes: bool,
    has_accepted_llm_items: bool,
    imported_modified: bool,
) -> ScenarioStatus:
    if origin_type == OriginType.EXCEL_IMPORT and not imported_modified:
        return ScenarioStatus.IMPORTADA
    if origin_type == OriginType.EXCEL_IMPORT and imported_modified:
        return ScenarioStatus.DERIVADA
    if origin_type == OriginType.DERIVED:
        return ScenarioStatus.DERIVADA
    if has_manual_changes or has_accepted_llm_items:
        return ScenarioStatus.WHAT_IF
    return ScenarioStatus.BASE


def determine_real_data_status(rows: list[PredictionRow]) -> str:
    if any(row.real_available for row in rows):
        return "datos reales disponibles"
    return "datos reales no disponibles"


def has_manual_scenario_changes(
    *,
    manual_overrides: list[dict[str, object]],
    calendar_modified: bool,
    events_modified: bool,
    weather_modified: bool,
) -> bool:
    return bool(manual_overrides) or calendar_modified or events_modified or weather_modified


def generate_range_warnings(
    *,
    start: date,
    end: date,
    coverage: CoverageSummary,
    reasonable_horizon_days: int,
    long_range_days: int = 31,
) -> list[WarningItem]:
    span_days = (end - start).days + 1
    warnings: list[WarningItem] = []

    if span_days > long_range_days:
        warnings.append(
            WarningItem(
                code="long_range",
                message="El rango es largo; revisa la interpretacion y agregaciones.",
            )
        )
    if coverage.event_days < coverage.total_days:
        warnings.append(
            WarningItem(
                code="missing_events",
                message="No hay eventos planificados para parte del rango.",
            )
        )
    if coverage.weather_days < coverage.total_days:
        warnings.append(
            WarningItem(
                code="missing_future_weather",
                message="No hay meteorologia disponible para parte del rango.",
            )
        )
    if coverage.calendar_days == coverage.total_days and coverage.event_days == 0 and coverage.weather_days == 0:
        warnings.append(
            WarningItem(
                code="calendar_only",
                message="Solo hay calendario disponible para el rango seleccionado.",
            )
        )
    if span_days > reasonable_horizon_days:
        warnings.append(
            WarningItem(
                code="model_horizon_exceeded",
                message="El rango excede el horizonte razonable validado del modelo.",
                severity="caution",
            )
        )

    return warnings
