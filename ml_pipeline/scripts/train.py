from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from _bootstrap import PROJECT_ROOT, bootstrap_src_path


bootstrap_src_path()

from metro_demand_models.configuration import load_settings
from metro_demand_models.evaluation.daily import build_temporal_splits, evaluate_forecasts
from metro_demand_models.models.tabular import train_tabular_model
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

    logger = logging.getLogger("metro_demand_models.scripts.train")
    manifest = load_daily_training_manifest(settings)
    feature_catalog = load_daily_feature_catalog(settings)

    for dataset_payload in manifest["datasets"]:
        dataset_path = Path(dataset_payload["dataset_path"])
        frame = pd.read_parquet(dataset_path)
        splits = build_temporal_splits(settings, frame)
        artifacts = train_tabular_model(
            settings,
            frame,
            splits,
            feature_columns=list(dataset_payload["feature_columns"]),
        )
        evaluation = evaluate_forecasts(artifacts.predictions)
        artifact_paths = save_experiment_outputs(
            settings,
            model_name="tabular_hgbr",
            variant=str(dataset_payload["variant"]),
            series_policy=str(dataset_payload["series_policy"]),
            horizon_days=int(dataset_payload["horizon_days"]),
            predictions=artifacts.predictions,
            evaluation=evaluation,
            feature_catalog=feature_catalog,
            selected_feature_columns=list(dataset_payload["feature_columns"]),
            metadata={
                "dataset_path": str(dataset_path),
                "variant": dataset_payload["variant"],
                "series_policy": dataset_payload["series_policy"],
                "horizon_days": int(dataset_payload["horizon_days"]),
                "feature_columns": list(dataset_payload["feature_columns"]),
                "transformed_feature_names": artifacts.transformed_feature_names,
                "splits": [split.to_dict() for split in splits],
            },
            model_object=artifacts.fitted_test_pipeline,
        )
        run_name = log_experiment_run(
            settings,
            model_name="tabular_hgbr",
            variant=str(dataset_payload["variant"]),
            series_policy=str(dataset_payload["series_policy"]),
            horizon_days=int(dataset_payload["horizon_days"]),
            feature_catalog=feature_catalog,
            selected_feature_columns=list(dataset_payload["feature_columns"]),
            evaluation=evaluation,
            artifact_paths=artifact_paths,
            extra_params={
                "dataset_path": str(dataset_path),
                "transformed_feature_count": len(artifacts.transformed_feature_names),
            },
        )
        test_row = evaluation.split_metrics.loc[evaluation.split_metrics["split_type"] == "test"].iloc[0]
        logger.info(
            "Logged %s | %s/%s/h%s | test_wape=%.4f | test_mae=%.4f | features=%s",
            run_name,
            dataset_payload["variant"],
            dataset_payload["series_policy"],
            dataset_payload["horizon_days"],
            float(test_row["wape"]),
            float(test_row["mae"]),
            len(dataset_payload["feature_columns"]),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
