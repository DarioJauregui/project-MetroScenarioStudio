from __future__ import annotations

from datetime import date

from metro_scenario_studio.domain.aggregations import aggregate_prediction_rows
from metro_scenario_studio.domain.rules import (
    determine_execution_status,
    determine_real_data_status,
    generate_range_warnings,
)
from metro_scenario_studio.domain.schemas import (
    CoverageSummary,
    OriginType,
    PredictionRow,
    ScenarioStatus,
)


def test_execution_status_marks_base_without_manual_changes() -> None:
    status = determine_execution_status(
        origin_type=OriginType.MANUAL,
        has_manual_changes=False,
        has_accepted_llm_items=False,
        imported_modified=False,
    )

    assert status == ScenarioStatus.BASE


def test_execution_status_marks_what_if_for_manual_or_llm_changes() -> None:
    manual_status = determine_execution_status(
        origin_type=OriginType.MANUAL,
        has_manual_changes=True,
        has_accepted_llm_items=False,
        imported_modified=False,
    )
    llm_status = determine_execution_status(
        origin_type=OriginType.MANUAL,
        has_manual_changes=False,
        has_accepted_llm_items=True,
        imported_modified=False,
    )

    assert manual_status == ScenarioStatus.WHAT_IF
    assert llm_status == ScenarioStatus.WHAT_IF


def test_execution_status_preserves_import_and_derivation_semantics() -> None:
    imported = determine_execution_status(
        origin_type=OriginType.EXCEL_IMPORT,
        has_manual_changes=False,
        has_accepted_llm_items=False,
        imported_modified=False,
    )
    derived = determine_execution_status(
        origin_type=OriginType.EXCEL_IMPORT,
        has_manual_changes=True,
        has_accepted_llm_items=False,
        imported_modified=True,
    )

    assert imported == ScenarioStatus.IMPORTADA
    assert derived == ScenarioStatus.DERIVADA


def test_real_data_status_is_available_when_any_prediction_has_real_value() -> None:
    rows = [
        PredictionRow(
            target_date=date(2026, 5, 20),
            linea="LINEA 1",
            estacion="Atarazanas",
            series_id="ATZ",
            station_abbrev="ATZ",
            network_order=1,
            y_pred=100.0,
            y_real=None,
            model_variant="strict_available",
            horizon_days=1,
        ),
        PredictionRow(
            target_date=date(2026, 5, 21),
            linea="LINEA 1",
            estacion="Atarazanas",
            series_id="ATZ",
            station_abbrev="ATZ",
            network_order=1,
            y_pred=110.0,
            y_real=112.0,
            model_variant="strict_available",
            horizon_days=1,
        ),
    ]

    assert determine_real_data_status(rows) == "datos reales disponibles"


def test_aggregate_prediction_rows_sums_from_station_line_rows() -> None:
    rows = [
        PredictionRow(
            target_date=date(2026, 5, 20),
            linea="LINEA 1",
            estacion="Atarazanas",
            series_id="ATZ",
            station_abbrev="ATZ",
            network_order=1,
            y_pred=100.0,
            y_real=90.0,
            model_variant="strict_available",
            horizon_days=1,
        ),
        PredictionRow(
            target_date=date(2026, 5, 20),
            linea="LINEA 1",
            estacion="Barbarela",
            series_id="BBL",
            station_abbrev="BBL",
            network_order=2,
            y_pred=50.0,
            y_real=60.0,
            model_variant="strict_available",
            horizon_days=1,
        ),
        PredictionRow(
            target_date=date(2026, 5, 21),
            linea="LINEA 2",
            estacion="La Isla",
            series_id="ISL",
            station_abbrev="ISL",
            network_order=20,
            y_pred=25.0,
            y_real=None,
            model_variant="strict_available",
            horizon_days=1,
        ),
    ]

    aggregates = aggregate_prediction_rows(rows)

    network_total = next(row for row in aggregates if row.level == "network" and row.target_date is None)
    line_total = next(row for row in aggregates if row.level == "line" and row.linea == "LINEA 1")
    date_total = next(row for row in aggregates if row.level == "network_date" and row.target_date == date(2026, 5, 20))

    assert network_total.y_pred == 175.0
    assert network_total.y_real == 150.0
    assert line_total.y_pred == 150.0
    assert date_total.y_pred == 150.0


def test_range_warnings_cover_long_range_missing_weather_events_and_horizon() -> None:
    warnings = generate_range_warnings(
        start=date(2026, 5, 1),
        end=date(2026, 6, 20),
        coverage=CoverageSummary(
            calendar_days=51,
            event_days=0,
            weather_days=0,
            total_days=51,
        ),
        reasonable_horizon_days=14,
    )

    codes = {warning.code for warning in warnings}

    assert "long_range" in codes
    assert "missing_events" in codes
    assert "missing_future_weather" in codes
    assert "calendar_only" in codes
    assert "model_horizon_exceeded" in codes
