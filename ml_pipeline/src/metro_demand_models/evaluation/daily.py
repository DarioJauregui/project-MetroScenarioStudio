from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from metro_demand_models.configuration import Settings


@dataclass(frozen=True)
class TemporalSplit:
    name: str
    split_type: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    score_start: pd.Timestamp
    score_end: pd.Timestamp

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value.isoformat() if isinstance(value, pd.Timestamp) else value for key, value in payload.items()}


@dataclass(frozen=True)
class EvaluationArtifacts:
    overall_metrics: pd.DataFrame
    split_metrics: pd.DataFrame
    line_metrics: pd.DataFrame
    series_metrics: pd.DataFrame


def build_temporal_splits(
    settings: Settings,
    frame: pd.DataFrame,
) -> list[TemporalSplit]:
    if frame.empty:
        raise ValueError("Cannot build temporal splits for an empty training frame.")

    split_settings = settings["daily_modeling"]["splits"]
    forecast_origin_column = str(settings["daily_modeling"]["forecast_origin_date_column"])
    origin_dates = pd.to_datetime(frame[forecast_origin_column]).sort_values().unique()
    origin_min = pd.Timestamp(origin_dates.min()).normalize()
    origin_max = pd.Timestamp(origin_dates.max()).normalize()

    test_window_days = int(split_settings["test_window_days"])
    validation_window_days = int(split_settings["validation_window_days"])
    validation_folds = int(split_settings["validation_folds"])
    min_history_days = int(split_settings["min_history_days"])

    test_start = origin_max - pd.Timedelta(days=test_window_days - 1)
    earliest_validation_start = test_start - pd.Timedelta(days=validation_window_days * validation_folds)
    if (earliest_validation_start - origin_min).days < min_history_days:
        raise ValueError("Not enough history to satisfy the configured temporal split policy.")

    splits: list[TemporalSplit] = []
    for reverse_index in range(validation_folds):
        fold_number = validation_folds - reverse_index
        score_end = test_start - pd.Timedelta(days=(reverse_index * validation_window_days) + 1)
        score_start = score_end - pd.Timedelta(days=validation_window_days - 1)
        splits.append(
            TemporalSplit(
                name=f"validation_fold_{fold_number}",
                split_type="validation",
                train_start=origin_min,
                train_end=score_start - pd.Timedelta(days=1),
                score_start=score_start,
                score_end=score_end,
            )
        )

    splits = list(sorted(splits, key=lambda split: split.score_start))
    splits.append(
        TemporalSplit(
            name="test",
            split_type="test",
            train_start=origin_min,
            train_end=test_start - pd.Timedelta(days=1),
            score_start=test_start,
            score_end=origin_max,
        )
    )
    return splits


def slice_split_frame(
    frame: pd.DataFrame,
    split: TemporalSplit,
    *,
    forecast_origin_column: str = "forecast_origin_date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    origin_dates = pd.to_datetime(frame[forecast_origin_column])
    train_mask = (origin_dates >= split.train_start) & (origin_dates <= split.train_end)
    score_mask = (origin_dates >= split.score_start) & (origin_dates <= split.score_end)
    train_frame = frame.loc[train_mask].copy()
    score_frame = frame.loc[score_mask].copy()
    return train_frame, score_frame


def evaluate_forecasts(predictions: pd.DataFrame) -> EvaluationArtifacts:
    required_columns = {
        "model_name",
        "variant",
        "series_policy",
        "horizon_days",
        "split_name",
        "split_type",
        "series_id",
        "linea",
        "estacion",
        "y_true",
        "y_pred",
    }
    missing_columns = required_columns.difference(predictions.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Prediction frame is missing required columns: {missing}.")

    overall_metrics = _aggregate_metrics(
        predictions,
        ["model_name", "variant", "series_policy", "horizon_days"],
    )
    split_metrics = _aggregate_metrics(
        predictions,
        ["model_name", "variant", "series_policy", "horizon_days", "split_name", "split_type"],
    )
    line_metrics = _aggregate_metrics(
        predictions,
        [
            "model_name",
            "variant",
            "series_policy",
            "horizon_days",
            "split_name",
            "split_type",
            "linea",
        ],
    )
    series_metrics = _aggregate_metrics(
        predictions,
        [
            "model_name",
            "variant",
            "series_policy",
            "horizon_days",
            "split_name",
            "split_type",
            "series_id",
            *(["series_label"] if "series_label" in predictions.columns else []),
            "linea",
            "estacion",
            *(["station_abbrev"] if "station_abbrev" in predictions.columns else []),
        ],
    )

    return EvaluationArtifacts(
        overall_metrics=overall_metrics,
        split_metrics=split_metrics,
        line_metrics=line_metrics,
        series_metrics=series_metrics,
    )


def select_recommended_series_policy(
    settings: Settings,
    split_metrics: pd.DataFrame,
    line_metrics: pd.DataFrame,
    *,
    model_name: str = "tabular_hgbr",
    variant: str = "strict_available",
) -> dict[str, Any]:
    threshold = float(settings["daily_modeling"]["sparse_exclusion_rel_wape_threshold"])
    line_guardrail = float(settings["daily_modeling"]["line_wape_guardrail_threshold"])
    strict_test = split_metrics.loc[
        (split_metrics["model_name"] == model_name)
        & (split_metrics["variant"] == variant)
        & (split_metrics["split_type"] == "test")
        & (split_metrics["series_policy"].isin(["all_series", "sparse_excluded"]))
    ].copy()
    strict_line_test = line_metrics.loc[
        (line_metrics["model_name"] == model_name)
        & (line_metrics["variant"] == variant)
        & (line_metrics["split_type"] == "test")
        & (line_metrics["series_policy"].isin(["all_series", "sparse_excluded"]))
    ].copy()

    horizon_results: list[dict[str, Any]] = []
    keep_sparse_excluded = True
    for horizon_days in sorted(strict_test["horizon_days"].unique()):
        horizon_frame = strict_test.loc[strict_test["horizon_days"] == horizon_days].set_index("series_policy")
        if not {"all_series", "sparse_excluded"}.issubset(horizon_frame.index):
            keep_sparse_excluded = False
            horizon_results.append(
                {
                    "horizon_days": int(horizon_days),
                    "decision_supported": False,
                    "reason": "missing_policy_results",
                }
            )
            continue

        wape_all = float(horizon_frame.loc["all_series", "wape"])
        wape_sparse_excluded = float(horizon_frame.loc["sparse_excluded", "wape"])
        relative_improvement = (wape_all - wape_sparse_excluded) / wape_all if wape_all else 0.0

        line_frame = strict_line_test.loc[
            strict_line_test["horizon_days"] == horizon_days,
            ["series_policy", "linea", "wape"],
        ]
        line_pivot = line_frame.pivot(index="linea", columns="series_policy", values="wape")
        worst_line_relative_change = 0.0
        line_guardrail_ok = True
        if {"all_series", "sparse_excluded"}.issubset(line_pivot.columns):
            relative_changes = (
                (line_pivot["sparse_excluded"] - line_pivot["all_series"]) / line_pivot["all_series"].replace(0, np.nan)
            ).fillna(0.0)
            worst_line_relative_change = float(relative_changes.max())
            line_guardrail_ok = bool((relative_changes <= line_guardrail).all())
        else:
            keep_sparse_excluded = False
            line_guardrail_ok = False

        horizon_supported = relative_improvement >= threshold and line_guardrail_ok
        keep_sparse_excluded &= horizon_supported
        horizon_results.append(
            {
                "horizon_days": int(horizon_days),
                "decision_supported": bool(horizon_supported),
                "wape_all_series": wape_all,
                "wape_sparse_excluded": wape_sparse_excluded,
                "relative_wape_improvement": relative_improvement,
                "line_guardrail_ok": line_guardrail_ok,
                "worst_line_relative_change": worst_line_relative_change,
            }
        )

    recommended_policy = "sparse_excluded" if keep_sparse_excluded and horizon_results else "all_series"
    return {
        "model_name": model_name,
        "variant": variant,
        "recommended_series_policy": recommended_policy,
        "decision_rule": {
            "global_relative_wape_threshold": threshold,
            "line_wape_guardrail_threshold": line_guardrail,
        },
        "horizon_results": horizon_results,
    }


def _aggregate_metrics(
    predictions: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in predictions.groupby(group_columns, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        metric_row = {column: value for column, value in zip(group_columns, keys)}
        metric_row.update(_compute_metrics(group))
        rows.append(metric_row)
    return pd.DataFrame(rows).sort_values(group_columns).reset_index(drop=True)


def _compute_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    available = frame.loc[frame["y_true"].notna() & frame["y_pred"].notna()].copy()
    available_count = int(len(available))
    total_count = int(len(frame))
    coverage_ratio = float(available_count / total_count) if total_count else np.nan
    if available.empty:
        return {
            "row_count": total_count,
            "available_prediction_count": available_count,
            "coverage_ratio": coverage_ratio,
            "mae": np.nan,
            "rmse": np.nan,
            "wape": np.nan,
            "smape": np.nan,
        }

    error = available["y_pred"] - available["y_true"]
    absolute_error = error.abs()
    mae = float(absolute_error.mean())
    rmse = float(np.sqrt(np.mean(np.square(error))))

    denominator = float(available["y_true"].abs().sum())
    wape = float(absolute_error.sum() / denominator) if denominator else np.nan

    smape_denominator = available["y_true"].abs() + available["y_pred"].abs()
    smape_components = np.where(
        smape_denominator == 0,
        0.0,
        2.0 * absolute_error / smape_denominator,
    )
    smape = float(np.mean(smape_components))

    return {
        "row_count": total_count,
        "available_prediction_count": available_count,
        "coverage_ratio": coverage_ratio,
        "mae": mae,
        "rmse": rmse,
        "wape": wape,
        "smape": smape,
    }
