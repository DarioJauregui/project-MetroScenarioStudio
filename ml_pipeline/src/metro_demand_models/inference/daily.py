from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from metro_demand_models.configuration import Settings, get_path
from metro_demand_models.training.daily import load_daily_training_dataset


@dataclass(frozen=True)
class PromotedModelSpec:
    model_name: str
    variant: str
    series_policy: str
    horizon_days: int
    dataset_path: Path
    model_path: Path
    metadata_path: Path
    feature_columns: list[str]


def load_promoted_model_specs(settings: Settings) -> list[PromotedModelSpec]:
    metrics_dir = get_path(settings, "daily_modeling_metrics_dir")
    models_dir = get_path(settings, "daily_modeling_models_dir")
    policy_path = metrics_dir / "series_policy_decision.json"
    if not policy_path.exists():
        raise FileNotFoundError(
            f"Series policy decision file not found: '{policy_path}'. Run scripts/evaluate.py first."
        )
    decision = json.loads(policy_path.read_text(encoding="utf-8"))
    recommended_policy = str(decision["recommended_series_policy"])
    primary_variant = str(settings["daily_modeling"]["target_variant_primary"])

    specs: list[PromotedModelSpec] = []
    for horizon_days in settings["daily_modeling"]["horizons"]:
        metadata_slug = f"tabular_hgbr__{primary_variant}__{recommended_policy}__h{int(horizon_days)}"
        metadata_path = metrics_dir / f"{metadata_slug}__metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Promoted model metadata not found: '{metadata_path}'. Run scripts/train.py first."
            )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        specs.append(
            PromotedModelSpec(
                model_name="tabular_hgbr",
                variant=primary_variant,
                series_policy=recommended_policy,
                horizon_days=int(horizon_days),
                dataset_path=Path(metadata["dataset_path"]),
                model_path=models_dir / f"{metadata_slug}.pkl",
                metadata_path=metadata_path,
                feature_columns=list(metadata["feature_columns"]),
            )
        )
    return specs


def run_daily_inference_smoke(
    settings: Settings,
    *,
    example_dates: list[str] | None = None,
    example_rows_per_horizon: int = 10,
) -> pd.DataFrame:
    predictions: list[pd.DataFrame] = []
    promoted_specs = load_promoted_model_specs(settings)

    for spec in promoted_specs:
        model = load_pickled_model(spec.model_path)
        frame = load_daily_training_dataset(
            settings,
            spec.variant,
            spec.horizon_days,
            series_policy=spec.series_policy,
        )
        target_frame = _select_inference_rows(
            frame,
            example_dates=example_dates,
            example_rows_per_horizon=example_rows_per_horizon,
        )
        smoke_predictions = target_frame[
            [
                "forecast_origin_date",
                "target_date",
                "series_id",
                "series_label",
                "linea",
                "estacion",
                "station_abbrev",
            ]
        ].copy()
        smoke_predictions["model_name"] = spec.model_name
        smoke_predictions["variant"] = spec.variant
        smoke_predictions["series_policy"] = spec.series_policy
        smoke_predictions["horizon_days"] = spec.horizon_days
        smoke_predictions["y_true_if_available"] = target_frame["trip_count_target"]
        smoke_predictions["y_pred"] = model.predict(target_frame[spec.feature_columns])
        predictions.append(smoke_predictions)

    return pd.concat(predictions, ignore_index=True)


def save_daily_inference_smoke_outputs(
    settings: Settings,
    predictions: pd.DataFrame,
) -> dict[str, str]:
    output_dir = get_path(settings, "daily_modeling_inference_dir")
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "recommended_inference_smoke.parquet"
    csv_path = output_dir / "recommended_inference_smoke.csv"
    predictions.to_parquet(parquet_path, index=False)
    predictions.to_csv(csv_path, index=False, encoding="utf-8")
    return {
        "parquet": str(parquet_path),
        "csv": str(csv_path),
    }


def load_pickled_model(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Model artifact not found: '{path}'. Run scripts/train.py first.")
    with path.open("rb") as file_handle:
        return pickle.load(file_handle)


def _select_inference_rows(
    frame: pd.DataFrame,
    *,
    example_dates: list[str] | None,
    example_rows_per_horizon: int,
) -> pd.DataFrame:
    working = frame.copy()
    working["forecast_origin_date"] = pd.to_datetime(working["forecast_origin_date"])
    if example_dates:
        requested_dates = {pd.Timestamp(date_value).normalize() for date_value in example_dates}
        subset = working.loc[working["forecast_origin_date"].isin(requested_dates)].copy()
        if subset.empty:
            raise ValueError(
                "None of the requested smoke inference dates are available in the promoted training dataset."
            )
        return subset.sort_values(["forecast_origin_date", "series_id"]).reset_index(drop=True)

    latest_dates = working["forecast_origin_date"].drop_duplicates().sort_values().tail(2).tolist()
    subset = working.loc[working["forecast_origin_date"].isin(latest_dates)].copy()
    subset = subset.sort_values(["forecast_origin_date", "series_id"])
    if len(subset) > example_rows_per_horizon * len(latest_dates):
        subset = subset.groupby("forecast_origin_date", group_keys=False).head(example_rows_per_horizon)
    return subset.reset_index(drop=True)
