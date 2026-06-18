from __future__ import annotations

from pathlib import Path

from metro_demand_models.configuration import load_settings
from metro_demand_models.data.contracts import (
    load_dataset_contracts,
    load_future_granular_contract,
    load_join_contracts,
    load_modeling_base_contract,
    load_series_contract,
    load_service_day_policy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_phase_2a_contracts_are_available_from_configuration() -> None:
    settings = load_settings(PROJECT_ROOT)

    dataset_contracts = load_dataset_contracts(settings)
    join_contracts = load_join_contracts(settings)
    modeling_contract = load_modeling_base_contract(settings)
    service_day_policy = load_service_day_policy(settings)
    series_contract = load_series_contract(settings)
    future_granular_contract = load_future_granular_contract(settings)

    assert "validations" in dataset_contracts
    assert dataset_contracts["validations"].granularity == "transaction"
    assert dataset_contracts["external_daily_features"].unique_key == ("date",)
    assert dataset_contracts["stations_master"].unique_key == ("linea", "estacion")

    assert "trips_to_external_daily_features" in join_contracts
    assert join_contracts["trips_to_external_daily_features"].required is True
    assert join_contracts["station_daily_to_network_changes"].missing_policy == "fill_zero"

    assert modeling_contract.name == "phase_2a_station_daily_model_base"
    assert modeling_contract.phase_scope == "phase_2a"
    assert modeling_contract.target_column == "trip_count"
    assert (
        "service_date",
        "series_id",
        "linea",
    ) == modeling_contract.identifier_columns[:3]
    assert "temp_mean_c" in modeling_contract.feature_columns
    assert "network_change_count" in modeling_contract.support_columns

    assert service_day_policy.policy == "natural_calendar_day"
    assert service_day_policy.boundary_hour == 0
    assert series_contract.series_id_column == "series_id"
    assert series_contract.natural_key_columns == ("linea", "station_join_key")
    assert future_granular_contract.status == "planned"
    assert future_granular_contract.example_interval == "15min"
