from __future__ import annotations

import json
import pickle

from fastapi.testclient import TestClient
import pandas as pd

from metro_scenario_studio.api.main import create_app
from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.domain.schemas import EventVariable, ScenarioExecution, ScenarioStatus
from metro_scenario_studio.services.prediction_service import PredictionService


class TinyPickledModel:
    def predict(self, frame):
        return (frame["target_latest_observed_value"].astype(float) + frame["calendar_day"].astype(float)).tolist()


class EventSensitivePickledModel:
    def predict(self, frame):
        return (frame["event_active_count"].astype(float) * 1000).tolist()


def test_api_creates_runs_exports_imports_and_derives_scenario(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    create_response = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-22",
            "author": "tester",
            "comment": "Escenario base",
        },
    )
    assert create_response.status_code == 201
    scenario_id = create_response.json()["id"]
    assert scenario_id.startswith("scn_20260520-20260522_base_")

    external_response = client.get(
        "/api/external-data",
        params={"start": "2026-05-20", "end": "2026-05-22"},
    )
    assert external_response.status_code == 200
    assert external_response.json()["coverage"]["total_days"] == 3

    run_response = client.post(f"/api/scenarios/{scenario_id}/run")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["execution"]["status"] == "base"
    assert run_payload["aggregates"][0]["level"] == "network"
    assert "narrative_summary" in run_payload
    assert run_payload["narrative_summary"] is None or isinstance(run_payload["narrative_summary"], str)

    export_response = client.post(f"/api/scenarios/{scenario_id}/export")
    assert export_response.status_code == 200
    export_path = export_response.json()["path"]

    import_response = client.post("/api/imports", json={"path": export_path})
    assert import_response.status_code == 201
    imported_id = import_response.json()["execution"]["id"]
    assert import_response.json()["execution"]["status"] == "importada"

    derive_response = client.post(
        f"/api/scenarios/{imported_id}/derive",
        json={"comment": "Copia editable"},
    )
    assert derive_response.status_code == 201
    assert derive_response.json()["status"] == "derivada"
    assert derive_response.json()["parent_execution_id"] == imported_id


def test_create_then_run_preserves_full_scenario_input_for_export_import(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    create_response = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-20",
            "manual_overrides": [{"type": "event", "field": "event", "target_date": "2026-05-20"}],
            "calendar_final": [
                {
                    "target_date": "2026-05-20",
                    "day_of_week": 2,
                    "is_holiday": True,
                    "source": "manual_scenario",
                    "modified": True,
                }
            ],
            "events_final": [
                {
                    "event_id": "manual_event",
                    "name": "Evento manual",
                    "target_date": "2026-05-20",
                    "event_type": "deportivo",
                    "impact_level": "alto",
                    "affected_stations": ["ATZ"],
                    "modified": True,
                }
            ],
            "weather_final": [
                {
                    "target_date": "2026-05-20",
                    "rain": True,
                    "heavy_rain": False,
                    "approx_temperature": 19,
                    "alert_level": "amarilla",
                    "source": "manual_scenario",
                    "modified": True,
                }
            ],
        },
    )
    assert create_response.status_code == 201
    scenario_id = create_response.json()["id"]

    run_payload = client.post(f"/api/scenarios/{scenario_id}/run").json()
    execution_input = run_payload["execution"]["input"]

    assert run_payload["execution"]["status"] == "what_if"
    assert execution_input["calendar_final"][0]["is_holiday"] is True
    assert execution_input["events_final"][0]["name"] == "Evento manual"
    assert execution_input["weather_final"][0]["alert_level"] == "amarilla"

    export_path = client.post(f"/api/scenarios/{scenario_id}/export").json()["path"]
    imported = client.post("/api/imports", json={"path": export_path}).json()

    assert imported["execution"]["input"]["events_final"][0]["target_date"] == "2026-05-20"
    assert imported["execution"]["input"]["weather_final"][0]["alert_level"] == "amarilla"


def test_excel_import_preserves_structured_event_range_fields(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-23",
            "manual_overrides": [{"type": "event", "field": "date_range"}],
            "events_final": [
                {
                    "event_id": "manual_range",
                    "name": "Congreso de prueba",
                    "target_date": "2026-05-20",
                    "date_mode": "range",
                    "start_date": "2026-05-20",
                    "end_date": "2026-05-22",
                    "selected_dates": [],
                    "all_day": False,
                    "start_time": "10:00",
                    "end_time": "18:00",
                    "event_type": "feria/congreso",
                    "impact_level": "alto",
                    "affected_stations": ["ATZ", "PCH1"],
                    "origin_event_id": "source-7",
                    "deleted": False,
                    "modified": True,
                }
            ],
        },
    ).json()["id"]
    client.post(f"/api/scenarios/{scenario_id}/run")

    export_path = client.post(f"/api/scenarios/{scenario_id}/export").json()["path"]
    imported = client.post("/api/imports", json={"path": export_path}).json()
    imported_event = imported["execution"]["input"]["events_final"][0]

    assert imported_event["date_mode"] == "range"
    assert imported_event["start_date"] == "2026-05-20"
    assert imported_event["end_date"] == "2026-05-22"
    assert imported_event["all_day"] is False
    assert imported_event["affected_stations"] == ["ATZ", "PCH1"]


def test_api_exposes_station_catalog_in_network_order_and_downloads_excel(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    stations_response = client.get("/api/stations")

    assert stations_response.status_code == 200
    stations = stations_response.json()
    assert stations[0]["station_abbrev"] == "ATZ"
    assert stations == sorted(stations, key=lambda item: (item["network_order"], item["series_id"]))

    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]
    client.post(f"/api/scenarios/{scenario_id}/run")
    download_response = client.post(f"/api/scenarios/{scenario_id}/export/download")

    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert download_response.content.startswith(b"PK")


def test_external_data_uses_readonly_real_feature_files_when_available(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    data_root = tmp_path / "data"
    features_dir = data_root / "processed" / "external_features"
    events_dir = data_root / "interim" / "operations"
    features_dir.mkdir(parents=True)
    events_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "date": "2026-05-20",
                "day_of_week": 2,
                "is_holiday": True,
                "holiday_name": "Test holiday",
                "is_preholiday": False,
                "is_postholiday": False,
                "temp_mean_c": 18.5,
                "temp_min_c": 15.0,
                "temp_max_c": 23.0,
                "precip_mm": 4.2,
                "rain_hours": 2,
                "wind_mean_kmh": 8,
                "humidity_mean_pct": 70,
                "weather_code": 61,
                "weather_source": "test_weather",
                "is_rainy_day": True,
                "is_heavy_rain_day": False,
                "is_hot_day": False,
                "is_cold_day": False,
                "is_bad_weather_day": True,
            }
        ]
    ).to_parquet(features_dir / "external_daily_features.parquet")
    pd.DataFrame(
        [
            {
                "event_id": 77,
                "title": "Evento real",
                "category": "DEPORTES",
                "start_ts": "2026-05-20 10:00:00",
                "end_ts": "2026-05-20 12:00:00",
                "start_date": "2026-05-20",
                "end_date": "2026-05-20",
                "attendance_estimated": 6000,
                "comments": "Fuente real de prueba",
            }
        ]
    ).to_parquet(events_dir / "events_normalized.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        data_root=data_root,
        metro_demand_models_root=models_root,
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/external-data", params={"start": "2026-05-20", "end": "2026-05-20"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["calendar"][0]["is_holiday"] is True
    assert payload["calendar"][0]["special_day"] == "Test holiday"
    assert payload["weather"][0]["rain"] is True
    assert payload["weather"][0]["source"] == "test_weather"
    assert payload["events"][0]["name"] == "Evento real"


def test_prediction_service_reads_real_model_predictions_with_actuals(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    predictions_dir = models_root / "artifacts" / "daily_modeling" / "predictions"
    predictions_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-17",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "variant": "strict_available",
                "model_name": "tabular_hgbr",
                "horizon_days": 1,
                "y_true": 7100.0,
                "y_pred": 7050.5,
            },
            {
                "target_date": "2026-05-17",
                "series_id": "PCH",
                "linea": "LINEA 2",
                "estacion": "Palacio de los Deportes",
                "station_abbrev": "PDD",
                "variant": "strict_available",
                "model_name": "tabular_hgbr",
                "horizon_days": 1,
                "y_true": 2400.0,
                "y_pred": 2450.0,
            },
        ]
    ).to_parquet(predictions_dir / "tabular_hgbr__strict_available__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_test",
        range_start=pd.Timestamp("2026-05-17").date(),
        range_end=pd.Timestamp("2026-05-17").date(),
    )

    rows = PredictionService(settings).predict(execution)

    assert len(rows) == 2
    atarazanas = next(row for row in rows if row.series_id == "ATZ")
    assert atarazanas.y_pred == 7050.5
    assert atarazanas.y_real == 7100.0
    assert atarazanas.model_variant == "strict_available"


def test_historical_ranges_are_marked_as_evaluated_with_leakage_warning(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    predictions_dir = models_root / "artifacts" / "daily_modeling" / "predictions"
    predictions_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-20",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "model_variant": "strict_available",
                "model_name": "tabular_hgbr",
                "y_pred": 1000,
                "y_true": 950,
            }
        ]
    ).to_parquet(predictions_dir / "tabular_hgbr__strict_available__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]

    payload = client.post(f"/api/scenarios/{scenario_id}/run").json()

    assert payload["execution"]["status"] == ScenarioStatus.HISTORICO_EVALUADO
    assert "historical_evaluation_leakage_risk" in payload["execution"]["warnings"]
    assert payload["prediction_rows"][0]["y_real"] == 950.0


def test_run_scenario_enriches_network_date_actuals_from_storage_csv(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    settings.storage_dir.mkdir(parents=True)
    settings.historical_demand_csv.write_text(
        "Fecha,Viajeros\n2026-05-20,43210\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]

    payload = client.post(f"/api/scenarios/{scenario_id}/run").json()

    network_date = next(row for row in payload["aggregates"] if row["level"] == "network_date")
    network = next(row for row in payload["aggregates"] if row["level"] == "network")
    assert payload["execution"]["real_data_status"] == "datos reales disponibles"
    assert network_date["target_date"] == "2026-05-20"
    assert network_date["y_real"] == 43210.0
    assert network_date["real_available"] is True
    assert network["y_real"] == 43210.0


def test_historical_what_if_keeps_what_if_status_with_real_data_warning(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    predictions_dir = models_root / "artifacts" / "daily_modeling" / "predictions"
    predictions_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-20",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "variant": "forecastable_scenario",
                "model_name": "tabular_hgbr",
                "y_pred": 1000,
                "y_true": 950,
            }
        ]
    ).to_parquet(predictions_dir / "tabular_hgbr__forecastable_scenario__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-20",
            "manual_overrides": [{"type": "weather", "field": "rain", "value": True}],
        },
    ).json()["id"]

    payload = client.post(f"/api/scenarios/{scenario_id}/run").json()

    assert payload["execution"]["status"] == "what_if"
    assert payload["execution"]["real_data_status"] == "datos reales disponibles"
    assert "historical_evaluation_leakage_risk" in payload["execution"]["warnings"]


def test_historical_what_if_prefers_pickled_model_inference_over_precomputed_predictions(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    predictions_dir = models_root / "artifacts" / "daily_modeling" / "predictions"
    metrics_dir = models_root / "artifacts" / "daily_modeling" / "metrics"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    training_dir = models_root / "artifacts" / "daily_modeling" / "training_data"
    predictions_dir.mkdir(parents=True)
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    training_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-20",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "variant": "forecastable_scenario",
                "model_name": "tabular_hgbr",
                "y_pred": 0,
                "y_true": 950,
            }
        ]
    ).to_parquet(predictions_dir / "tabular_hgbr__forecastable_scenario__all_series__h1.parquet")
    metadata = {
        "feature_columns": [
            "calendar_day",
            "target_latest_observed_value",
            "series_id",
            "linea",
            "station_group",
            "zone",
            "event_active_count",
        ],
        "dataset_path": str(training_dir / "daily_training__forecastable_scenario__all_series__h1.parquet"),
        "horizon_days": 1,
        "series_policy": "all_series",
    }
    (metrics_dir / "tabular_hgbr__forecastable_scenario__all_series__h1__metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    with (models_dir / "tabular_hgbr__forecastable_scenario__all_series__h1.pkl").open("wb") as file_handle:
        pickle.dump(EventSensitivePickledModel(), file_handle)
    pd.DataFrame(
        [
            {
                "forecast_origin_date": "2026-05-19",
                "target_date": "2026-05-20",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "station_group": "centro",
                "zone": "A",
                "trip_count_target": 950.0,
                "calendar_day": 20,
                "target_latest_observed_value": 900.0,
                "event_active_count": 0.0,
            }
        ]
    ).to_parquet(training_dir / "daily_training__forecastable_scenario__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_historical_what_if",
        range_start=pd.Timestamp("2026-05-20").date(),
        range_end=pd.Timestamp("2026-05-20").date(),
        model_variant="forecastable_scenario",
    )
    execution.input.manual_overrides = [{"type": "event", "field": "event"}]
    execution.input.events_final = [
        EventVariable(
            event_id="evt_manual",
            name="Partido",
            target_date="2026-05-20",
            event_type="deportivo",
            impact_level="alto",
            affected_stations=["ATZ"],
            modified=True,
        )
    ]

    rows = PredictionService(settings).predict(execution)

    assert rows[0].prediction_mode == "model_inference"
    assert rows[0].y_pred == 1000.0
    assert rows[0].y_real == 950.0


def test_what_if_overrides_precomputed_future_features_before_model_inference(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    metrics_dir = models_root / "artifacts" / "daily_modeling" / "metrics"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    forecast_dir = models_root / "artifacts" / "daily_modeling" / "future_forecasts"
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    forecast_dir.mkdir(parents=True)
    metadata = {
        "feature_columns": [
            "calendar_day",
            "target_latest_observed_value",
            "series_id",
            "linea",
            "station_group",
            "zone",
            "event_active_count",
        ],
        "dataset_path": str(models_root / "missing_training_data.parquet"),
        "horizon_days": 1,
        "series_policy": "all_series",
    }
    (metrics_dir / "tabular_hgbr__forecastable_scenario__all_series__h1__metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    with (models_dir / "tabular_hgbr__forecastable_scenario__all_series__h1.pkl").open("wb") as file_handle:
        pickle.dump(EventSensitivePickledModel(), file_handle)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-20",
                "forecast_origin_date": "2026-05-19",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "model_variant": "forecastable_scenario",
                "horizon_days": 1,
                "calendar_day": 20,
                "target_latest_observed_value": 900.0,
                "station_group": "centro",
                "zone": "A",
                "event_active_count": 0.0,
                "y_pred": 0.0,
            }
        ]
    ).to_parquet(forecast_dir / "future_forecast_series.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_future_what_if",
        range_start=pd.Timestamp("2026-05-20").date(),
        range_end=pd.Timestamp("2026-05-20").date(),
        model_variant="forecastable_scenario",
    )
    execution.input.manual_overrides = [{"type": "event", "field": "event"}]
    execution.input.events_final = [
        EventVariable(
            event_id="evt_manual",
            name="Partido",
            target_date="2026-05-20",
            event_type="deportivo",
            impact_level="alto",
            affected_stations=["ATZ"],
            modified=True,
        )
    ]

    rows = PredictionService(settings).predict(execution)

    assert rows[0].prediction_mode == "model_inference"
    assert rows[0].y_pred == 1000.0


def test_prediction_service_does_not_fabricate_rows_when_real_artifacts_have_no_coverage(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    predictions_dir = models_root / "artifacts" / "daily_modeling" / "predictions"
    predictions_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-17",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "variant": "strict_available",
                "model_name": "tabular_hgbr",
                "horizon_days": 1,
                "y_true": 7100.0,
                "y_pred": 7050.5,
            }
        ]
    ).to_parquet(predictions_dir / "tabular_hgbr__strict_available__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_test",
        range_start=pd.Timestamp("2024-01-01").date(),
        range_end=pd.Timestamp("2024-01-02").date(),
    )

    rows = PredictionService(settings).predict(execution)

    assert rows == []


def test_prediction_service_runs_pickled_model_for_future_inference(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    metrics_dir = models_root / "artifacts" / "daily_modeling" / "metrics"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    training_dir = models_root / "artifacts" / "daily_modeling" / "training_data"
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    training_dir.mkdir(parents=True)

    metadata = {
        "feature_columns": [
            "calendar_day",
            "target_latest_observed_value",
            "series_id",
            "linea",
            "station_group",
            "zone",
        ],
        "dataset_path": str(training_dir / "daily_training__strict_available__all_series__h1.parquet"),
        "horizon_days": 1,
        "series_policy": "all_series",
    }
    (metrics_dir / "tabular_hgbr__strict_available__all_series__h1__metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    with (models_dir / "tabular_hgbr__strict_available__all_series__h1.pkl").open("wb") as file_handle:
        pickle.dump(TinyPickledModel(), file_handle)
    pd.DataFrame(
        [
            {
                "forecast_origin_date": "2026-05-17",
                "target_date": "2026-05-18",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "station_group": "centro",
                "zone": "A",
                "trip_count_target": 1000.0,
                "calendar_day": 18,
                "target_latest_observed_value": 900.0,
            }
        ]
    ).to_parquet(training_dir / "daily_training__strict_available__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_future",
        range_start=pd.Timestamp("2026-05-19").date(),
        range_end=pd.Timestamp("2026-05-19").date(),
    )

    rows = PredictionService(settings).predict(execution)

    assert len(rows) == 1
    assert rows[0].target_date.isoformat() == "2026-05-19"
    assert rows[0].y_pred == 1019.0
    assert rows[0].y_real is None


def test_prediction_service_recomputes_future_forecast_rows_with_pickled_model(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    metrics_dir = models_root / "artifacts" / "daily_modeling" / "metrics"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    forecast_dir = models_root / "artifacts" / "daily_modeling" / "future_forecasts"
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    forecast_dir.mkdir(parents=True)

    metadata = {
        "feature_columns": [
            "calendar_day",
            "target_latest_observed_value",
            "series_id",
            "linea",
            "station_group",
            "zone",
        ],
        "dataset_path": str(models_root / "missing_training_data.parquet"),
        "horizon_days": 1,
        "series_policy": "all_series",
    }
    (metrics_dir / "tabular_hgbr__strict_available__all_series__h1__metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    with (models_dir / "tabular_hgbr__strict_available__all_series__h1.pkl").open("wb") as file_handle:
        pickle.dump(TinyPickledModel(), file_handle)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-19",
                "forecast_origin_date": "2026-05-18",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "model_variant": "strict_available",
                "horizon_days": 1,
                "calendar_day": 19,
                "target_latest_observed_value": 900.0,
                "station_group": "centro",
                "zone": "A",
                "y_pred": 1.0,
            }
        ]
    ).to_parquet(forecast_dir / "future_forecast_series.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_future_forecast_recompute",
        range_start=pd.Timestamp("2026-05-19").date(),
        range_end=pd.Timestamp("2026-05-19").date(),
    )

    rows = PredictionService(settings).predict(execution)

    assert len(rows) == 1
    assert rows[0].y_pred == 919.0
    assert rows[0].prediction_mode == "model_inference"
    assert rows[0].model_artifact_sha256


def test_run_scenario_warns_when_long_future_inference_uses_recursive_forecast_features(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    metrics_dir = models_root / "artifacts" / "daily_modeling" / "metrics"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    forecast_dir = models_root / "artifacts" / "daily_modeling" / "future_forecasts"
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    forecast_dir.mkdir(parents=True)

    metadata = {
        "feature_columns": [
            "calendar_day",
            "target_latest_observed_value",
            "series_id",
            "linea",
            "station_group",
            "zone",
        ],
        "dataset_path": str(models_root / "missing_training_data.parquet"),
        "horizon_days": 1,
        "series_policy": "all_series",
    }
    (metrics_dir / "tabular_hgbr__strict_available__all_series__h1__metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    with (models_dir / "tabular_hgbr__strict_available__all_series__h1.pkl").open("wb") as file_handle:
        pickle.dump(TinyPickledModel(), file_handle)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-19",
                "forecast_origin_date": "2026-05-18",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "model_variant": "strict_available",
                "horizon_days": 1,
                "calendar_day": 19,
                "target_latest_observed_value": 900.0,
                "station_group": "centro",
                "zone": "A",
                "y_pred": 1.0,
            },
            {
                "target_date": "2026-05-20",
                "forecast_origin_date": "2026-05-19",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "model_variant": "strict_available",
                "horizon_days": 1,
                "calendar_day": 20,
                "target_latest_observed_value": 919.0,
                "station_group": "centro",
                "zone": "A",
                "y_pred": 1.0,
            },
        ]
    ).to_parquet(forecast_dir / "future_forecast_series.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
        reasonable_horizon_days=1,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-19", "range_end": "2026-05-20"},
    ).json()["id"]

    payload = client.post(f"/api/scenarios/{scenario_id}/run").json()

    assert {row["prediction_mode"] for row in payload["prediction_rows"]} == {"model_inference"}
    assert "recursive_future_inference_horizon_exceeded" in payload["execution"]["warnings"]


def test_forecastable_inference_uses_event_date_ranges(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    metrics_dir = models_root / "artifacts" / "daily_modeling" / "metrics"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    training_dir = models_root / "artifacts" / "daily_modeling" / "training_data"
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    training_dir.mkdir(parents=True)

    metadata = {
        "feature_columns": [
            "calendar_day",
            "target_latest_observed_value",
            "series_id",
            "linea",
            "station_group",
            "zone",
            "event_active_count",
        ],
        "dataset_path": str(training_dir / "daily_training__forecastable_scenario__all_series__h1.parquet"),
        "horizon_days": 1,
        "series_policy": "all_series",
    }
    (metrics_dir / "tabular_hgbr__forecastable_scenario__all_series__h1__metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    with (models_dir / "tabular_hgbr__forecastable_scenario__all_series__h1.pkl").open("wb") as file_handle:
        pickle.dump(EventSensitivePickledModel(), file_handle)
    pd.DataFrame(
        [
            {
                "forecast_origin_date": "2026-05-17",
                "target_date": "2026-05-18",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "station_group": "centro",
                "zone": "A",
                "trip_count_target": 1000.0,
                "calendar_day": 18,
                "target_latest_observed_value": 1000.0,
                "event_active_count": 0.0,
            }
        ]
    ).to_parquet(training_dir / "daily_training__forecastable_scenario__all_series__h1.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    execution = ScenarioExecution(
        id="scn_event_range",
        range_start=pd.Timestamp("2026-05-19").date(),
        range_end=pd.Timestamp("2026-05-21").date(),
        model_variant="forecastable_scenario",
    )
    execution.input.events_final = [
        EventVariable(
            event_id="evt_range",
            name="Congreso",
            target_date="2026-05-19",
            start_date="2026-05-19",
            end_date="2026-05-20",
            event_type="feria/congreso",
            impact_level="alto",
            affected_stations=["ATZ"],
            modified=True,
        )
    ]

    rows = PredictionService(settings).predict(execution)

    by_date = {row.target_date.isoformat(): row.y_pred for row in rows}
    assert by_date["2026-05-19"] == 1000.0
    assert by_date["2026-05-20"] == 1000.0
    assert by_date["2026-05-21"] == 0.0


def test_mock_prediction_never_marks_fabricated_actuals_as_real_data(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    execution = ScenarioExecution(
        id="scn_mock",
        range_start=pd.Timestamp("2026-05-17").date(),
        range_end=pd.Timestamp("2026-05-17").date(),
    )

    rows = PredictionService(settings).predict(execution)

    assert rows
    assert all(row.y_real is None for row in rows)


def test_external_data_does_not_create_synthetic_weather_or_events_without_real_sources(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=False,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/external-data", params={"start": "2026-05-20", "end": "2026-05-23"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"] == []
    assert payload["weather"] == []
    assert payload["coverage"]["event_days"] == 0
    assert payload["coverage"]["weather_days"] == 0


def test_run_scenario_warns_when_real_model_predictions_are_unavailable(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    (models_root / "artifacts" / "daily_modeling" / "predictions").mkdir(parents=True)
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-21"},
    ).json()["id"]

    response = client.post(f"/api/scenarios/{scenario_id}/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["prediction_rows"] == []
    assert "model_predictions_unavailable" in payload["execution"]["warnings"]


def test_run_scenario_warns_when_using_precomputed_forecast_fallback(tmp_path) -> None:
    models_root = tmp_path / "readonly-models"
    forecast_dir = models_root / "artifacts" / "daily_modeling" / "future_forecasts"
    forecast_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "target_date": "2026-05-19",
                "forecast_origin_date": "2026-05-18",
                "series_id": "ATZ",
                "linea": "LINEA 1",
                "estacion": "Atarazanas",
                "station_abbrev": "ATZ",
                "network_order": 1,
                "model_variant": "strict_available",
                "horizon_days": 1,
                "y_pred": 1234.0,
            }
        ]
    ).to_parquet(forecast_dir / "future_forecast_series.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=False,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-19", "range_end": "2026-05-19"},
    ).json()["id"]

    payload = client.post(f"/api/scenarios/{scenario_id}/run").json()

    assert payload["prediction_rows"][0]["prediction_mode"] == "precomputed_forecast_fallback"
    assert "model_inference_unavailable" in payload["execution"]["warnings"]
    assert "precomputed_forecast_fallback_used" in payload["execution"]["warnings"]


def test_api_updates_scenario_inputs_and_runs_as_what_if(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-20",
            "comment": "Original",
        },
    ).json()["id"]

    update_response = client.patch(
        f"/api/scenarios/{scenario_id}",
        json={
            "comment": "Escenario editado",
            "manual_overrides": [{"type": "event", "field": "impact_level", "value": "alto"}],
            "events_final": [
                {
                    "event_id": "manual_1",
                    "name": "Partido del Malaga",
                    "target_date": "2026-05-20",
                    "event_type": "deportivo",
                    "impact_level": "alto",
                    "affected_stations": ["ATZ", "PCH"],
                    "comment": "Alta afluencia esperada",
                    "source": "usuario",
                    "modified": True,
                    "used_by_model": True,
                }
            ],
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["comment"] == "Escenario editado"
    assert update_response.json()["input"]["events_final"][0]["name"] == "Partido del Malaga"

    run_response = client.post(f"/api/scenarios/{scenario_id}/run")

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["execution"]["status"] == "what_if"
    assert payload["execution"]["model_variant"] == "forecastable_scenario"


def test_api_uploads_excel_file_and_exposes_result_endpoint(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]
    client.post(f"/api/scenarios/{scenario_id}/run")
    export_path = client.post(f"/api/scenarios/{scenario_id}/export").json()["path"]

    with open(export_path, "rb") as file_handle:
        upload_response = client.post(
            "/api/imports/upload",
            files={
                "file": (
                    "scenario.xlsx",
                    file_handle,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert upload_response.status_code == 201
    imported_id = upload_response.json()["execution"]["id"]
    result_response = client.get(f"/api/scenarios/{imported_id}/result")

    assert result_response.status_code == 200
    assert result_response.json()["execution"]["status"] == "importada"
    assert len(result_response.json()["prediction_rows"]) > 0


def test_nlp_parse_requires_date_before_applying_changes(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/nlp/parse",
        json={
            "comment": "Partido del Malaga con lluvia y ambiente en redes sociales",
            "range_start": "2026-05-20",
            "range_end": "2026-05-20",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_human_validation"] is True
    assert payload["detected_items"] == []
    assert payload["not_used"][0]["reason"] == "missing_date"


def test_metrics_endpoint_exposes_model_registry_snapshot(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["promoted_model"]["model_name"] == "tabular_hgbr"
    assert "baseline_naive_seasonal_weekly" in payload["baselines"]


def test_health_endpoint_exposes_llm_runtime_configuration(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
        explanation_llm_enabled=True,
        explanation_llm_endpoint="http://127.0.0.1:1234/v1/chat/completions",
        explanation_llm_model="qwen3.6-35b-a3b",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["explanation_llm_enabled"] is True
    assert payload["explanation_llm_endpoint"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert payload["explanation_llm_model"] == "qwen3.6-35b-a3b"


def test_api_exposes_traceability_artifacts_and_external_snapshot(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-21",
            "author": "tester",
        },
    ).json()["id"]

    client.post(f"/api/scenarios/{scenario_id}/run")
    client.post(f"/api/scenarios/{scenario_id}/export")

    audit_response = client.get(f"/api/scenarios/{scenario_id}/audit")
    artifacts_response = client.get(f"/api/scenarios/{scenario_id}/artifacts")
    snapshot_response = client.get(f"/api/scenarios/{scenario_id}/external-snapshot")

    assert audit_response.status_code == 200
    assert [event["action"] for event in audit_response.json()] == ["run_prediction", "export_excel"]
    assert artifacts_response.status_code == 200
    assert artifacts_response.json()[0]["artifact_type"] == "export"
    assert artifacts_response.json()[0]["checksum"]
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["coverage"]["total_days"] == 2
    assert snapshot_response.json()["warnings"]


def test_api_compares_two_executed_scenarios_with_absolute_and_percent_deltas(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    base_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]
    what_if_id = client.post(
        "/api/scenarios",
        json={
            "range_start": "2026-05-20",
            "range_end": "2026-05-20",
            "manual_overrides": [{"type": "weather", "field": "rain", "value": True}],
        },
    ).json()["id"]

    client.post(f"/api/scenarios/{base_id}/run")
    client.post(f"/api/scenarios/{what_if_id}/run")

    response = client.get(
        "/api/scenarios/compare",
        params={"base_id": base_id, "candidate_id": what_if_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_execution_id"] == base_id
    assert payload["candidate_execution_id"] == what_if_id
    network_row = next(row for row in payload["rows"] if row["level"] == "network")
    assert network_row["delta_abs"] > 0
    assert network_row["delta_pct"] > 0
    assert "Escenario comparado por suma" in payload["notes"][0]


def test_audit_events_are_append_only_across_reruns(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]

    client.post(f"/api/scenarios/{scenario_id}/run")
    client.post(f"/api/scenarios/{scenario_id}/export")
    client.post(f"/api/scenarios/{scenario_id}/run")

    response = client.get(f"/api/scenarios/{scenario_id}/audit")

    assert response.status_code == 200
    actions = [event["action"] for event in response.json()]
    assert actions == ["run_prediction", "export_excel", "run_prediction"]


def test_api_explain_endpoint(tmp_path) -> None:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
        explanation_llm_enabled=True,
        explanation_llm_timeout_seconds=0.1,
    )
    client = TestClient(create_app(settings))
    scenario_id = client.post(
        "/api/scenarios",
        json={"range_start": "2026-05-20", "range_end": "2026-05-20"},
    ).json()["id"]

    run_response = client.post(f"/api/scenarios/{scenario_id}/run")
    assert run_response.status_code == 200

    explain_response = client.post(f"/api/scenarios/{scenario_id}/explain")
    assert explain_response.status_code == 200
    explain_payload = explain_response.json()
    assert "narrative_summary" in explain_payload
    assert explain_payload["narrative_summary"] is not None
    assert "El resumen LLM local no esta disponible" in explain_payload["narrative_summary"]
    assert "prediction_rows" in explain_payload
    assert len(explain_payload["prediction_rows"]) > 0
    assert "aggregates" in explain_payload
    assert len(explain_payload["aggregates"]) > 0
