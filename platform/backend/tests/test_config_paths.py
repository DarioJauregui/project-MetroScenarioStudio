from __future__ import annotations

from pathlib import Path

from metro_scenario_studio.core.config import get_settings


def test_get_settings_resolves_default_relative_paths_from_platform_root(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MSS_STORAGE_DIR", raising=False)
    monkeypatch.delenv("MSS_SQLITE_PATH", raising=False)
    monkeypatch.delenv("MSS_METRO_DEMAND_MODELS_ROOT", raising=False)
    monkeypatch.delenv("MSS_HISTORICAL_DEMAND_CSV", raising=False)

    settings = get_settings()

    platform_root = Path(__file__).resolve().parents[2]
    assert settings.storage_dir == platform_root / "storage"
    assert settings.sqlite_path == platform_root / "storage" / "metro_scenario_studio.db"
    assert settings.data_root == platform_root.parent / "data"
    assert settings.metro_demand_models_root == platform_root.parent / "ml_pipeline"
    assert settings.historical_demand_csv == platform_root / "storage" / "demanda_historica_MM.csv"


def test_get_settings_allows_data_root_override(monkeypatch, tmp_path) -> None:
    data_root = tmp_path / "scenario-data"
    monkeypatch.setenv("MSS_DATA_ROOT", str(data_root))

    settings = get_settings()

    assert settings.data_root == data_root


def test_get_settings_allows_historical_demand_csv_override(monkeypatch, tmp_path) -> None:
    csv_path = tmp_path / "real_demand" / "demanda_historica_MM.csv"
    monkeypatch.setenv("MSS_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("MSS_HISTORICAL_DEMAND_CSV", str(csv_path))

    settings = get_settings()

    assert settings.historical_demand_csv == csv_path


def test_prometheus_metrics_endpoint(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from metro_scenario_studio.api.main import create_app
    from metro_scenario_studio.core.config import Settings

    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=tmp_path / "readonly-models",
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "mss_model_wape" in response.text
    assert "mss_model_drift" in response.text


def test_prometheus_metrics_reads_drift_report_from_ml_pipeline_root(tmp_path) -> None:
    import json

    from fastapi.testclient import TestClient
    from metro_scenario_studio.api.main import create_app
    from metro_scenario_studio.core.config import Settings

    models_root = tmp_path / "ml_pipeline"
    drift_dir = models_root / "artifacts" / "monitoring"
    drift_dir.mkdir(parents=True)
    (drift_dir / "drift_metrics.json").write_text(
        json.dumps(
            {
                "drift_metrics": {
                    "demand_validations": {
                        "status": "drifted",
                        "p_value": 0.012,
                        "psi": 0.25,
                        "drift_detected": True,
                    },
                    "weather_features": {
                        "temp_mean_c": {
                            "status": "stable",
                            "p_value": 0.8,
                            "psi": 0.04,
                            "drift_detected": False,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    response = client.get("/metrics")

    assert response.status_code == 200
    assert 'mss_model_drift_p_value{feature="validaciones"} 0.012' in response.text
    assert 'mss_model_drift_detected{feature="temp_mean_c"} 0.0' in response.text


def test_prometheus_metrics_exposes_operational_state_files(tmp_path) -> None:
    import json

    from fastapi.testclient import TestClient
    from metro_scenario_studio.api.main import create_app
    from metro_scenario_studio.core.config import Settings

    models_root = tmp_path / "ml_pipeline"
    monitoring_dir = models_root / "artifacts" / "monitoring"
    models_dir = models_root / "artifacts" / "models" / "daily_modeling"
    monitoring_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    (models_dir / "tabular_hgbr__strict_available__all_series__h1.pkl").write_bytes(b"model")
    (monitoring_dir / "monitoring_summary.json").write_text(
        json.dumps({"global_status": "critical", "checks": {"data_drift": {"status": "drifted"}}}),
        encoding="utf-8",
    )
    (monitoring_dir / "pipeline_run_summary.json").write_text(
        json.dumps({"global_status": "success", "steps": [{"name": "train", "status": "success"}]}),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        metro_demand_models_root=models_root,
        use_mock_inference=True,
    )
    client = TestClient(create_app(settings))

    response = client.get("/metrics")

    assert response.status_code == 200
    assert 'mss_monitoring_status{status="critical"} 1.0' in response.text
    assert 'mss_pipeline_last_run_status{status="success"} 1.0' in response.text
    assert "mss_model_artifact_age_seconds" in response.text
