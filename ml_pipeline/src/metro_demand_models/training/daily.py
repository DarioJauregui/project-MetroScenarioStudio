from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from metro_demand_models.configuration import Settings, dump_settings, get_path
from metro_demand_models.evaluation.daily import EvaluationArtifacts
from metro_demand_models.features.daily import (
    DailyModelingFoundation,
    build_daily_modeling_foundation,
    build_daily_training_dataset,
)
from metro_demand_models.utils.tracking import configure_mlflow_tracking
from metro_demand_models.utils.run_metadata import build_artifact_manifest, git_revision, utc_now_iso, write_json


@dataclass(frozen=True)
class DailyDatasetSpec:
    variant: str
    series_policy: str
    horizon_days: int

    @property
    def slug(self) -> str:
        return f"{self.variant}__{self.series_policy}__h{self.horizon_days}"


def build_and_persist_daily_training_datasets(
    settings: Settings,
    *,
    variants: list[str] | None = None,
    series_policies: list[str] | None = None,
    horizons: list[int] | None = None,
    foundation: DailyModelingFoundation | None = None,
) -> dict[str, Any]:
    resolved_foundation = foundation or build_daily_modeling_foundation(settings)
    dataset_specs = list_daily_dataset_specs(
        settings,
        variants=variants,
        series_policies=series_policies,
        horizons=horizons,
    )
    training_dir = ensure_directory(get_path(settings, "daily_training_data_dir"))
    feature_catalog_path = training_dir / "feature_catalog.csv"
    panel_diagnostics_path = training_dir / "panel_diagnostics.csv"
    manifest_path = training_dir / "dataset_manifest.json"
    effective_settings_path = training_dir / "effective_settings.json"

    resolved_foundation.feature_catalog.to_csv(
        feature_catalog_path,
        index=False,
        encoding="utf-8",
    )
    resolved_foundation.panel_diagnostics.to_csv(
        panel_diagnostics_path,
        index=False,
        encoding="utf-8",
    )
    effective_settings_path.write_text(dump_settings(settings), encoding="utf-8")

    dataset_metadata: list[dict[str, Any]] = []
    for spec in dataset_specs:
        dataset = build_daily_training_dataset(
            settings,
            spec.variant,
            spec.horizon_days,
            series_policy=spec.series_policy,
            foundation=resolved_foundation,
        )
        dataset_path = get_daily_training_dataset_path(settings, spec)
        ensure_directory(dataset_path.parent)
        dataset.frame.to_parquet(dataset_path, index=False)
        metadata_path = dataset_path.with_suffix(".json")
        metadata_payload = {
            **dataset.metadata,
            "dataset_path": str(dataset_path),
            "metadata_path": str(metadata_path),
        }
        metadata_path.write_text(
            json.dumps(metadata_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        dataset_metadata.append(metadata_payload)

    manifest_payload = {
        "training_dir": str(training_dir),
        "feature_catalog_path": str(feature_catalog_path),
        "panel_diagnostics_path": str(panel_diagnostics_path),
        "effective_settings_path": str(effective_settings_path),
        "datasets": dataset_metadata,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_payload


def list_daily_dataset_specs(
    settings: Settings,
    *,
    variants: list[str] | None = None,
    series_policies: list[str] | None = None,
    horizons: list[int] | None = None,
) -> list[DailyDatasetSpec]:
    configured_variants = variants or list(settings["daily_modeling"]["available_variants"])
    configured_policies = series_policies or ["all_series", "sparse_excluded"]
    configured_horizons = horizons or [int(value) for value in settings["daily_modeling"]["horizons"]]

    return [
        DailyDatasetSpec(
            variant=str(variant),
            series_policy=str(series_policy),
            horizon_days=int(horizon_days),
        )
        for variant in configured_variants
        for series_policy in configured_policies
        for horizon_days in configured_horizons
    ]


def load_daily_training_dataset(
    settings: Settings,
    variant: str,
    horizon_days: int,
    *,
    series_policy: str,
) -> pd.DataFrame:
    dataset_path = get_daily_training_dataset_path(
        settings,
        DailyDatasetSpec(
            variant=variant,
            series_policy=series_policy,
            horizon_days=horizon_days,
        ),
    )
    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Daily training dataset not found: '{dataset_path}'. Run scripts/build_daily_training_dataset.py first."
        )
    return pd.read_parquet(dataset_path)


def load_daily_feature_catalog(settings: Settings) -> pd.DataFrame:
    path = get_path(settings, "daily_training_data_dir") / "feature_catalog.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Feature catalog not found: '{path}'. Run scripts/build_daily_training_dataset.py first."
        )
    return pd.read_csv(path)


def load_daily_panel_diagnostics(settings: Settings) -> pd.DataFrame:
    path = get_path(settings, "daily_training_data_dir") / "panel_diagnostics.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Panel diagnostics not found: '{path}'. Run scripts/build_daily_training_dataset.py first."
        )
    diagnostics = pd.read_csv(path, parse_dates=["first_observed_date", "last_observed_date"])
    return diagnostics


def load_daily_training_manifest(settings: Settings) -> dict[str, Any]:
    path = get_path(settings, "daily_training_data_dir") / "dataset_manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Daily training manifest not found: '{path}'. Run scripts/build_daily_training_dataset.py first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def get_daily_training_dataset_path(
    settings: Settings,
    spec: DailyDatasetSpec,
) -> Path:
    training_dir = get_path(settings, "daily_training_data_dir")
    return training_dir / f"daily_training__{spec.slug}.parquet"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_experiment_outputs(
    settings: Settings,
    *,
    model_name: str,
    variant: str,
    series_policy: str,
    horizon_days: int,
    predictions: pd.DataFrame,
    evaluation: EvaluationArtifacts,
    feature_catalog: pd.DataFrame,
    selected_feature_columns: list[str],
    metadata: dict[str, Any],
    model_object: Any | None = None,
) -> dict[str, str]:
    slug = f"{model_name}__{variant}__{series_policy}__h{horizon_days}"
    predictions_dir = ensure_directory(get_path(settings, "daily_modeling_predictions_dir"))
    metrics_dir = ensure_directory(get_path(settings, "daily_modeling_metrics_dir"))
    models_dir = ensure_directory(get_path(settings, "daily_modeling_models_dir"))

    prediction_path = predictions_dir / f"{slug}.parquet"
    overall_metrics_path = metrics_dir / f"{slug}__overall.csv"
    split_metrics_path = metrics_dir / f"{slug}__split.csv"
    line_metrics_path = metrics_dir / f"{slug}__line.csv"
    series_metrics_path = metrics_dir / f"{slug}__series.csv"
    feature_subset_path = metrics_dir / f"{slug}__features.csv"
    metadata_path = metrics_dir / f"{slug}__metadata.json"
    run_manifest_path = metrics_dir / f"{slug}__run_manifest.json"

    predictions.to_parquet(prediction_path, index=False)
    evaluation.overall_metrics.to_csv(overall_metrics_path, index=False, encoding="utf-8")
    evaluation.split_metrics.to_csv(split_metrics_path, index=False, encoding="utf-8")
    evaluation.line_metrics.to_csv(line_metrics_path, index=False, encoding="utf-8")
    evaluation.series_metrics.to_csv(series_metrics_path, index=False, encoding="utf-8")
    feature_catalog.loc[feature_catalog["feature_name"].isin(selected_feature_columns)].to_csv(
        feature_subset_path, index=False, encoding="utf-8"
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    artifact_paths = {
        "predictions": str(prediction_path),
        "overall_metrics": str(overall_metrics_path),
        "split_metrics": str(split_metrics_path),
        "line_metrics": str(line_metrics_path),
        "series_metrics": str(series_metrics_path),
        "feature_subset": str(feature_subset_path),
        "metadata": str(metadata_path),
    }

    if model_object is not None:
        model_path = models_dir / f"{slug}.pkl"
        with model_path.open("wb") as file_handle:
            pickle.dump(model_object, file_handle)
        artifact_paths["model"] = str(model_path)

    dataset_path = metadata.get("dataset_path")
    run_manifest = {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "code_version": git_revision(settings["runtime"]["project_root"]),
        "model": {
            "model_name": model_name,
            "variant": variant,
            "series_policy": series_policy,
            "horizon_days": int(horizon_days),
        },
        "data": {
            "dataset_path": str(dataset_path) if dataset_path else "unknown",
            "dataset_sha256": None,
            "feature_columns": selected_feature_columns,
        },
        "tracking": {
            "mlflow_experiment": str(settings["daily_modeling"]["mlflow"]["experiment_name"]),
            "mlflow_tracking_uri": str(settings.get("mlflow", {}).get("tracking_uri", "")),
        },
        "artifacts": build_artifact_manifest(artifact_paths),
        "metadata": metadata,
    }
    if dataset_path:
        from metro_demand_models.utils.run_metadata import file_sha256

        run_manifest["data"]["dataset_sha256"] = file_sha256(str(dataset_path))
    write_json(run_manifest_path, run_manifest)
    artifact_paths["run_manifest"] = str(run_manifest_path)

    return artifact_paths


def log_experiment_run(
    settings: Settings,
    *,
    model_name: str,
    variant: str,
    series_policy: str,
    horizon_days: int,
    feature_catalog: pd.DataFrame,
    selected_feature_columns: list[str],
    evaluation: EvaluationArtifacts,
    artifact_paths: dict[str, str],
    extra_params: dict[str, Any] | None = None,
) -> str:
    import mlflow

    tracking_uri = configure_mlflow_tracking(settings)
    experiment_name = str(settings["daily_modeling"]["mlflow"]["experiment_name"])
    mlflow.set_experiment(experiment_name)

    selected_catalog = feature_catalog.loc[feature_catalog["feature_name"].isin(selected_feature_columns)].copy()
    feature_availability_counts = selected_catalog.groupby("availability_class")["feature_name"].count().to_dict()
    feature_groups = sorted(selected_catalog["feature_group"].dropna().unique().tolist())
    feature_group_counts = selected_catalog.groupby("feature_group")["feature_name"].count().to_dict()
    test_metrics = evaluation.split_metrics.loc[evaluation.split_metrics["split_type"] == "test"].copy()
    if test_metrics.empty:
        raise ValueError("Cannot log MLflow metrics without a test split summary.")
    test_metrics_row = test_metrics.iloc[0].to_dict()

    params: dict[str, Any] = {
        "model_family": _infer_model_family(model_name),
        "model_name": model_name,
        "variant": variant,
        "series_policy": series_policy,
        "horizon_days": int(horizon_days),
        "target_transform": "none",
        "feature_groups": json.dumps(feature_groups),
        "feature_group_counts": json.dumps(feature_group_counts),
        "feature_columns": json.dumps(selected_feature_columns),
        "feature_availability_counts": json.dumps(feature_availability_counts),
        "tracking_uri": tracking_uri,
    }
    if extra_params:
        params.update(extra_params)

    run_name = f"{model_name}__{variant}__{series_policy}__h{horizon_days}"
    with mlflow.start_run(run_name=run_name):
        for key, value in params.items():
            mlflow.log_param(key, _serialize_mlflow_value(value))
        for metric_name in ["mae", "rmse", "wape", "smape", "coverage_ratio"]:
            if metric_name in test_metrics_row and pd.notna(test_metrics_row[metric_name]):
                mlflow.log_metric(f"test_{metric_name}", float(test_metrics_row[metric_name]))
        for artifact_path in artifact_paths.values():
            mlflow.log_artifact(artifact_path)
    return run_name


def _serialize_mlflow_value(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str)


def _infer_model_family(model_name: str) -> str:
    if model_name.startswith("baseline_"):
        return "baseline"
    if model_name.startswith("tabular_"):
        return "tabular"
    return "other"
