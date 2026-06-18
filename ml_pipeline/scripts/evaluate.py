from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import get_path, load_settings
from metro_demand_models.evaluation.daily import select_recommended_series_policy
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    settings = load_settings(PROJECT_ROOT)
    configure_logging(str(settings.get("logging", {}).get("level", "INFO")))

    logger = logging.getLogger("metro_demand_models.scripts.evaluate")
    metrics_dir = get_path(settings, "daily_modeling_metrics_dir")
    reports_dir = Path(metrics_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    split_metrics = _load_metric_table(reports_dir, "*__split.csv")
    line_metrics = _load_metric_table(reports_dir, "*__line.csv")
    overall_metrics = _load_metric_table(reports_dir, "*__overall.csv")

    policy_decision = select_recommended_series_policy(
        settings,
        split_metrics,
        line_metrics,
    )
    policy_path = reports_dir / "series_policy_decision.json"
    policy_path.write_text(
        json.dumps(policy_decision, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    recommended_policy = str(policy_decision["recommended_series_policy"])
    test_summary = split_metrics.loc[split_metrics["split_type"] == "test"].copy()
    test_summary["selected_for_final_comparison"] = (
        (test_summary["variant"] == "strict_available") & (test_summary["series_policy"] == recommended_policy)
    ) | ((test_summary["variant"] == "forecastable_scenario") & (test_summary["series_policy"] == recommended_policy))
    comparison_path = reports_dir / "comparison_summary.csv"
    test_summary.to_csv(comparison_path, index=False, encoding="utf-8")

    overall_path = reports_dir / "overall_summary.csv"
    overall_metrics.to_csv(overall_path, index=False, encoding="utf-8")

    logger.info(
        "Recommended series policy: %s | decision file: %s",
        recommended_policy,
        policy_path,
    )
    for horizon_days in sorted(test_summary["horizon_days"].unique()):
        horizon_frame = test_summary.loc[
            (test_summary["horizon_days"] == horizon_days) & test_summary["selected_for_final_comparison"]
        ].sort_values(["variant", "model_name"])
        if horizon_frame.empty:
            continue
        logger.info("Test comparison for horizon D+%s:", horizon_days)
        for row in horizon_frame.itertuples(index=False):
            logger.info(
                "  %s | %s/%s | WAPE=%.4f | MAE=%.4f | RMSE=%.4f | sMAPE=%.4f",
                row.model_name,
                row.variant,
                row.series_policy,
                float(row.wape),
                float(row.mae),
                float(row.rmse),
                float(row.smape),
            )
    logger.info("Comparison summary: %s", comparison_path)
    return 0


def _load_metric_table(directory: Path, pattern: str) -> pd.DataFrame:
    paths = sorted(directory.glob(pattern))
    if not paths:
        raise FileNotFoundError(
            f"No metric files matching '{pattern}' were found in '{directory}'. "
            "Run scripts/run_baselines.py and scripts/train.py first."
        )
    frames = [pd.read_csv(path) for path in paths]
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    raise SystemExit(main())
