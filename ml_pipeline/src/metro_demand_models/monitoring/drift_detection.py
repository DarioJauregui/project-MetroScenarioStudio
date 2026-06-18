from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)


def calculate_psi(baseline: np.ndarray, target: np.ndarray, num_buckets: int = 10) -> float:
    """Calculate the Population Stability Index (PSI) between baseline and target distributions."""
    # Filter out NaNs
    baseline = baseline[~np.isnan(baseline)]
    target = target[~np.isnan(target)]

    if len(baseline) == 0 or len(target) == 0:
        return 0.0

    # Determine bin edges based on baseline percentiles
    percentiles = np.linspace(0, 100, num_buckets + 1)
    bins = np.percentile(baseline, percentiles)
    # Ensure bin edges are unique to prevent duplicate bins
    bins = np.unique(bins)
    if len(bins) < 2:
        return 0.0

    # Adjust edges slightly to include boundary values
    bins[0] -= 1e-5
    bins[-1] += 1e-5

    # Compute frequencies
    baseline_counts, _ = np.histogram(baseline, bins=bins)
    target_counts, _ = np.histogram(target, bins=bins)

    # Convert to proportions with Laplace smoothing to avoid division by zero
    baseline_props = (baseline_counts + 0.5) / (len(baseline) + 0.5 * len(baseline_counts))
    target_props = (target_counts + 0.5) / (len(target) + 0.5 * len(target_counts))

    # Calculate PSI
    psi_value = np.sum((target_props - baseline_props) * np.log(target_props / baseline_props))
    return float(psi_value)


def check_distribution_drift(
    baseline_series: pd.Series, target_series: pd.Series, alpha: float = 0.05
) -> dict[str, Any]:
    """Run KS-test and PSI to detect drift between baseline and target."""
    baseline_vals = baseline_series.dropna().to_numpy()
    target_vals = target_series.dropna().to_numpy()

    if len(baseline_vals) < 10 or len(target_vals) < 10:
        return {
            "drift_detected": False,
            "p_value": 1.0,
            "ks_statistic": 0.0,
            "psi": 0.0,
            "status": "insufficient_data",
        }

    # Kolmogorov-Smirnov Test
    ks_res = ks_2samp(baseline_vals, target_vals)
    p_value = float(ks_res.pvalue)
    ks_stat = float(ks_res.statistic)

    # PSI calculation
    psi_val = calculate_psi(baseline_vals, target_vals)

    # Drift is detected if KS test is significant (p-value < alpha) and PSI is substantial
    # Standard PSI thresholds: < 0.1 (stable), 0.1-0.25 (moderate shift), > 0.25 (significant shift)
    drift_detected = p_value < alpha or psi_val > 0.25

    return {
        "drift_detected": bool(drift_detected),
        "p_value": p_value,
        "ks_statistic": ks_stat,
        "psi": psi_val,
        "status": "drifted" if drift_detected else "stable",
    }


def run_drift_monitoring(monorepo_root: Path) -> dict[str, Any]:
    """Evaluate drift on model target (demand/validations) and weather features."""
    logger.info("Starting ML model drift monitoring...")

    # 1. Load Data sources
    validations_path = monorepo_root / "data" / "processed" / "validaciones" / "validaciones_consolidado.parquet"
    weather_path = monorepo_root / "data" / "processed" / "external_features" / "external_daily_features.parquet"

    metrics: dict[str, Any] = {}

    # Run validations/demand drift (Concept Drift)
    if validations_path.exists():
        try:
            logger.info("Loading validations dataset for concept drift analysis...")
            # We aggregate validations to daily totals
            df_val = pd.read_parquet(validations_path, columns=["dia", "viajes_deducidos"])
            df_val["dia"] = pd.to_datetime(df_val["dia"])
            df_daily = df_val.groupby("dia")["viajes_deducidos"].sum().reset_index()

            # Define baseline (historical, older than 60 days) and target (recent 30 days)
            max_date = df_daily["dia"].max()
            baseline_cutoff = max_date - pd.Timedelta(days=60)
            target_cutoff = max_date - pd.Timedelta(days=30)

            baseline_data = df_daily[df_daily["dia"] < baseline_cutoff]["viajes_deducidos"]
            target_data = df_daily[df_daily["dia"] >= target_cutoff]["viajes_deducidos"]

            drift_res = check_distribution_drift(baseline_data, target_data)
            metrics["demand_validations"] = drift_res
            logger.info(
                "Concept drift (demand) checked: status=%s, p_value=%.4f, psi=%.4f",
                drift_res["status"],
                drift_res["p_value"],
                drift_res["psi"],
            )
        except Exception as e:
            logger.error("Failed to run concept drift check on validations: %s", e, exc_info=True)
            metrics["demand_validations"] = {"status": "error", "message": str(e)}
    else:
        logger.warning("Validations consolidado not found at %s. Skipping concept drift.", validations_path)
        metrics["demand_validations"] = {"status": "missing_data"}

    # Run weather feature drift (Data Drift)
    if weather_path.exists():
        try:
            logger.info("Loading weather features for data drift analysis...")
            df_weather = pd.read_parquet(weather_path)
            date_column = "fecha" if "fecha" in df_weather.columns else "date" if "date" in df_weather.columns else None
            if date_column:
                df_weather[date_column] = pd.to_datetime(df_weather[date_column])
                max_date = df_weather[date_column].max()
                baseline_cutoff = max_date - pd.Timedelta(days=60)
                target_cutoff = max_date - pd.Timedelta(days=30)

                features_to_monitor = [
                    column
                    for column in [
                        "temp_max_c",
                        "temp_min_c",
                        "temp_mean_c",
                        "precip_mm",
                        "temp_max",
                        "temp_min",
                        "prcp",
                    ]
                    if column in df_weather.columns
                ]
                metrics["weather_features"] = {}

                for feat in features_to_monitor:
                    baseline_data = df_weather[df_weather[date_column] < baseline_cutoff][feat]
                    target_data = df_weather[df_weather[date_column] >= target_cutoff][feat]
                    drift_res = check_distribution_drift(baseline_data, target_data)
                    metrics["weather_features"][feat] = drift_res
                    logger.info(
                        "Data drift (weather feature: %s) checked: status=%s, p_value=%.4f, psi=%.4f",
                        feat,
                        drift_res["status"],
                        drift_res["p_value"],
                        drift_res["psi"],
                    )
                if not features_to_monitor:
                    metrics["weather_features"] = {"status": "missing_features"}
            else:
                logger.warning("Weather dataset did not contain expected date column.")
                metrics["weather_features"] = {"status": "missing_date_column"}
        except Exception as e:
            logger.error("Failed to run data drift check on weather features: %s", e, exc_info=True)
            metrics["weather_features"] = {"status": "error", "message": str(e)}
    else:
        logger.warning("Weather features not found at %s. Skipping data drift.", weather_path)
        metrics["weather_features"] = {"status": "missing_data"}

    # Save monitoring report to artifacts
    artifacts_monitoring_dir = monorepo_root / "ml_pipeline" / "artifacts" / "monitoring"
    artifacts_monitoring_dir.mkdir(parents=True, exist_ok=True)

    report_path = artifacts_monitoring_dir / "drift_metrics.json"
    summary_path = artifacts_monitoring_dir / "monitoring_summary.json"
    summary = _build_monitoring_summary(metrics, report_path)
    report_data = {"timestamp": pd.Timestamp.now().isoformat(), "drift_metrics": metrics, "summary": summary}

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info("Drift monitoring report persisted to %s", report_path)
    return report_data


def _build_monitoring_summary(metrics: dict[str, Any], report_path: Path) -> dict[str, Any]:
    concept_status = _status_from_metric(metrics.get("demand_validations"))
    weather_metrics = metrics.get("weather_features")
    data_status = _status_from_metric(weather_metrics)
    statuses = [concept_status, data_status]
    if any(status in {"error", "drifted"} for status in statuses):
        global_status = "critical"
    elif any(status in {"missing_data", "insufficient_data"} for status in statuses):
        global_status = "warning"
    else:
        global_status = "ok"
    return {
        "schema_version": 1,
        "timestamp": pd.Timestamp.now().isoformat(),
        "global_status": global_status,
        "drift_report_path": str(report_path),
        "checks": {
            "concept_drift": {"status": concept_status, "source": "demand_validations"},
            "data_drift": {"status": data_status, "source": "weather_features"},
        },
    }


def _status_from_metric(value: Any) -> str:
    if isinstance(value, dict) and "status" in value:
        return str(value["status"])
    if isinstance(value, dict):
        child_statuses = [_status_from_metric(child) for child in value.values()]
        if any(status in {"error", "drifted"} for status in child_statuses):
            return "drifted"
        if any(status in {"missing_data", "insufficient_data"} for status in child_statuses):
            return "insufficient_data"
        if child_statuses:
            return "stable"
    return "missing_data"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--monorepo-root", type=str, required=True, help="Absolute path to project root")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_drift_monitoring(Path(args.monorepo_root))
