from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from metro_scenario_studio.api.dependencies import get_settings, get_scenario_service
from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.services.scenario_service import ScenarioService

router = APIRouter(tags=["metrics"])


@router.get("/api/metrics")
def metrics(scenario_service: ScenarioService = Depends(get_scenario_service)):
    return scenario_service.metrics()


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(
    settings: Settings = Depends(get_settings),
    scenario_service: ScenarioService = Depends(get_scenario_service),
) -> str:
    lines = []

    # 1. Model Performance Metrics
    lines.append("# HELP mss_model_wape Weighted Absolute Percentage Error of the model")
    lines.append("# TYPE mss_model_wape gauge")
    lines.append("# HELP mss_model_smape Symmetric Mean Absolute Percentage Error of the model")
    lines.append("# TYPE mss_model_smape gauge")

    try:
        model_data = scenario_service.metrics()
        metrics_list = model_data.get("metrics", [])
        if isinstance(metrics_list, list):
            for m in metrics_list:
                model_name = m.get("model_name", "unknown")
                variant = m.get("variant", "unknown")
                wape = m.get("wape")
                smape = m.get("smape")

                if wape is not None:
                    try:
                        lines.append(f'mss_model_wape{{model_name="{model_name}",variant="{variant}"}} {float(wape)}')
                    except ValueError:
                        pass
                if smape is not None:
                    try:
                        lines.append(f'mss_model_smape{{model_name="{model_name}",variant="{variant}"}} {float(smape)}')
                    except ValueError:
                        pass
    except Exception as e:
        lines.append(f"# Error reading model performance metrics: {e}")

    # 2. Model Drift Metrics
    lines.append(
        "# HELP mss_model_drift_p_value P-value of Kolmogorov-Smirnov test for feature/target distribution drift"
    )
    lines.append("# TYPE mss_model_drift_p_value gauge")
    lines.append("# HELP mss_model_drift_psi Population Stability Index (PSI) for feature/target distribution drift")
    lines.append("# TYPE mss_model_drift_psi gauge")
    lines.append("# HELP mss_model_drift_detected Flag indicating if drift was detected (1) or not (0)")
    lines.append("# TYPE mss_model_drift_detected gauge")

    drift_report_path = settings.metro_demand_models_root / "artifacts" / "monitoring" / "drift_metrics.json"
    if drift_report_path.exists():
        try:
            with drift_report_path.open("r", encoding="utf-8") as f:
                report = json.load(f)
            drift_data = report.get("drift_metrics", {})

            # Demand validation target drift
            demand = drift_data.get("demand_validations", {})
            if isinstance(demand, dict) and demand.get("status") in ("stable", "drifted"):
                p_val = demand.get("p_value", 1.0)
                psi_val = demand.get("psi", 0.0)
                detected = 1.0 if demand.get("drift_detected", False) else 0.0
                lines.append(f'mss_model_drift_p_value{{feature="validaciones"}} {p_val}')
                lines.append(f'mss_model_drift_psi{{feature="validaciones"}} {psi_val}')
                lines.append(f'mss_model_drift_detected{{feature="validaciones"}} {detected}')

            # Weather features drift
            weather = drift_data.get("weather_features", {})
            if isinstance(weather, dict):
                for feat, res in weather.items():
                    if isinstance(res, dict) and res.get("status") in ("stable", "drifted"):
                        p_val = res.get("p_value", 1.0)
                        psi_val = res.get("psi", 0.0)
                        detected = 1.0 if res.get("drift_detected", False) else 0.0
                        lines.append(f'mss_model_drift_p_value{{feature="{feat}"}} {p_val}')
                        lines.append(f'mss_model_drift_psi{{feature="{feat}"}} {psi_val}')
                        lines.append(f'mss_model_drift_detected{{feature="{feat}"}} {detected}')
        except Exception as e:
            lines.append(f"# Error reading drift metrics: {e}")
    else:
        lines.append("# Drift report file does not exist yet")

    monitoring_dir = settings.metro_demand_models_root / "artifacts" / "monitoring"
    monitoring_summary_path = monitoring_dir / "monitoring_summary.json"
    pipeline_summary_path = monitoring_dir / "pipeline_run_summary.json"
    model_path = (
        settings.metro_demand_models_root
        / "artifacts"
        / "models"
        / "daily_modeling"
        / "tabular_hgbr__strict_available__all_series__h1.pkl"
    )

    lines.append("# HELP mss_monitoring_status Monitoring global status as labeled gauge")
    lines.append("# TYPE mss_monitoring_status gauge")
    monitoring_summary = _read_json(monitoring_summary_path)
    monitoring_status = str(monitoring_summary.get("global_status", "missing"))
    lines.append(f'mss_monitoring_status{{status="{_label(monitoring_status)}"}} 1.0')

    lines.append("# HELP mss_pipeline_last_run_status Last pipeline run global status as labeled gauge")
    lines.append("# TYPE mss_pipeline_last_run_status gauge")
    pipeline_summary = _read_json(pipeline_summary_path)
    pipeline_status = str(pipeline_summary.get("global_status", "missing"))
    lines.append(f'mss_pipeline_last_run_status{{status="{_label(pipeline_status)}"}} 1.0')

    lines.append("# HELP mss_model_artifact_age_seconds Age in seconds of promoted strict model artifact")
    lines.append("# TYPE mss_model_artifact_age_seconds gauge")
    model_age = _file_age_seconds(model_path)
    if model_age is not None:
        lines.append(f"mss_model_artifact_age_seconds {model_age}")

    lines.append("# HELP mss_external_features_age_seconds Age in seconds of external daily features parquet")
    lines.append("# TYPE mss_external_features_age_seconds gauge")
    features_age = _file_age_seconds(
        settings.data_root / "processed" / "external_features" / "external_daily_features.parquet"
    )
    if features_age is not None:
        lines.append(f"mss_external_features_age_seconds {features_age}")

    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    return round((datetime.now(UTC).timestamp() - path.stat().st_mtime), 3)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
