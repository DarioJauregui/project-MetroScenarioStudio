from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.evaluation.daily import build_temporal_splits, evaluate_forecasts
from metro_demand_models.models.baselines import run_baselines
from metro_demand_models.training.daily import (
    load_daily_feature_catalog,
    load_daily_training_manifest,
    log_experiment_run,
    save_experiment_outputs,
)
from metro_demand_models.utils.logging import configure_logging


def main() -> int:
    settings = load_settings(PROJECT_ROOT)
    configure_logging(str(settings.get("logging", {}).get("level", "INFO")))
    logger = logging.getLogger("metro_demand_models.scripts.run_baselines")

    manifest = load_daily_training_manifest(settings)
    feature_catalog = load_daily_feature_catalog(settings)
    for dataset_payload in manifest["datasets"]:
        dataset_path = Path(dataset_payload["dataset_path"])
        frame = pd.read_parquet(dataset_path)
        splits = build_temporal_splits(settings, frame)
        predictions = run_baselines(frame, splits)

        for model_name in sorted(predictions["model_name"].unique()):
            model_predictions = predictions.loc[predictions["model_name"] == model_name].copy()
            evaluation = evaluate_forecasts(model_predictions)
            artifact_paths = save_experiment_outputs(
                settings,
                model_name=model_name,
                variant=str(dataset_payload["variant"]),
                series_policy=str(dataset_payload["series_policy"]),
                horizon_days=int(dataset_payload["horizon_days"]),
                predictions=model_predictions,
                evaluation=evaluation,
                feature_catalog=feature_catalog,
                selected_feature_columns=[model_name],
                metadata={
                    "dataset_path": str(dataset_path),
                    "variant": dataset_payload["variant"],
                    "series_policy": dataset_payload["series_policy"],
                    "horizon_days": int(dataset_payload["horizon_days"]),
                    "splits": [split.to_dict() for split in splits],
                },
            )
            run_name = log_experiment_run(
                settings,
                model_name=model_name,
                variant=str(dataset_payload["variant"]),
                series_policy=str(dataset_payload["series_policy"]),
                horizon_days=int(dataset_payload["horizon_days"]),
                feature_catalog=feature_catalog,
                selected_feature_columns=[model_name],
                evaluation=evaluation,
                artifact_paths=artifact_paths,
                extra_params={
                    "dataset_path": str(dataset_path),
                    "baseline_type": model_name,
                },
            )
            test_row = evaluation.split_metrics.loc[evaluation.split_metrics["split_type"] == "test"].iloc[0]
            logger.info(
                "Logged %s | %s/%s/h%s | test_wape=%.4f | test_mae=%.4f",
                run_name,
                dataset_payload["variant"],
                dataset_payload["series_policy"],
                dataset_payload["horizon_days"],
                float(test_row["wape"]),
                float(test_row["mae"]),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
