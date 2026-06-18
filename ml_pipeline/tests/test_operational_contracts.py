from __future__ import annotations

from pathlib import Path

from metro_demand_models.configuration import load_settings
from metro_demand_models.data.contracts import (
    load_operational_output_contracts,
    load_workbook_source_contracts,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_operational_contracts_load_from_base_configuration() -> None:
    settings = load_settings(PROJECT_ROOT)

    source_contracts = load_workbook_source_contracts(settings)
    output_contracts = load_operational_output_contracts(settings)

    assert set(source_contracts) == {
        "services_history",
        "events_calendar",
        "event_locations",
        "incidents_history",
    }
    assert source_contracts["services_history"].sheet_name == "Resumen_Servicios"
    assert source_contracts["services_history"].file_glob.startswith("Servicios Hist")

    assert {
        "services_history_daily",
        "services_line_daily",
        "events_normalized",
        "events_station_impact",
        "events_station_daily",
        "events_phase2a_series_daily",
        "incidents_normalized",
        "incidents_daily",
        "events_mapping_report",
        "incidents_mapping_report",
        "inspection_summary",
    }.issubset(set(output_contracts))
