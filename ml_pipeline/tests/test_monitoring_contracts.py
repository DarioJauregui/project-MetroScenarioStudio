from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from metro_demand_models.monitoring.drift_detection import run_drift_monitoring


def test_drift_monitoring_writes_standard_summary_when_sources_are_missing(tmp_path: Path) -> None:
    report = run_drift_monitoring(tmp_path)

    monitoring_dir = tmp_path / "ml_pipeline" / "artifacts" / "monitoring"
    summary_path = monitoring_dir / "monitoring_summary.json"

    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["global_status"] == "warning"
    assert summary["checks"]["concept_drift"]["status"] == "missing_data"
    assert summary["checks"]["data_drift"]["status"] == "missing_data"
    assert summary["drift_report_path"] == str(monitoring_dir / "drift_metrics.json")
    assert report["summary"]["global_status"] == "warning"


def test_drift_monitoring_reads_current_external_features_schema(tmp_path: Path) -> None:
    weather_dir = tmp_path / "data" / "processed" / "external_features"
    weather_dir.mkdir(parents=True)
    dates = pd.date_range("2026-01-01", periods=100, freq="D")
    pd.DataFrame(
        {
            "date": dates,
            "temp_max_c": [20 + (idx % 5) for idx in range(100)],
            "temp_min_c": [10 + (idx % 4) for idx in range(100)],
            "precip_mm": [0.0 if idx < 70 else 5.0 for idx in range(100)],
        }
    ).to_parquet(weather_dir / "external_daily_features.parquet")

    report = run_drift_monitoring(tmp_path)

    weather = report["drift_metrics"]["weather_features"]
    assert "temp_max_c" in weather
    assert "temp_min_c" in weather
    assert "precip_mm" in weather
