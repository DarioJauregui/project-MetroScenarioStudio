from __future__ import annotations

import pandas as pd

from metro_demand_models.evaluation.daily import TemporalSplit, slice_split_frame


BASELINE_COLUMNS = {
    "baseline_naive_simple": "baseline_naive_simple",
    "baseline_naive_seasonal_weekly": "baseline_naive_seasonal_weekly",
}


def run_baselines(
    frame: pd.DataFrame,
    splits: list[TemporalSplit],
) -> pd.DataFrame:
    required_columns = {
        "forecast_origin_date",
        "target_date",
        "series_id",
        "linea",
        "estacion",
        "trip_count_target",
        *BASELINE_COLUMNS.values(),
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Baseline frame is missing required columns: {missing}.")

    predictions: list[pd.DataFrame] = []
    required_context_columns = [
        "forecast_origin_date",
        "target_date",
        "series_id",
        "linea",
        "estacion",
        "trip_count_target",
    ]
    optional_context_columns = [
        "series_label",
        "station_abbrev",
        "variant",
        "feature_variant",
        "series_policy",
        "horizon_days",
    ]
    available_context_columns = required_context_columns + [
        column for column in optional_context_columns if column in frame.columns
    ]

    for split in splits:
        _, score_frame = slice_split_frame(frame, split)
        for model_name, baseline_column in BASELINE_COLUMNS.items():
            prediction_frame = score_frame[available_context_columns].copy()
            if "variant" not in prediction_frame.columns and "feature_variant" in prediction_frame.columns:
                prediction_frame["variant"] = prediction_frame["feature_variant"]
            prediction_frame["model_name"] = model_name
            prediction_frame["split_name"] = split.name
            prediction_frame["split_type"] = split.split_type
            prediction_frame["y_true"] = prediction_frame["trip_count_target"]
            prediction_frame["y_pred"] = score_frame[baseline_column]
            predictions.append(prediction_frame)

    return pd.concat(predictions, ignore_index=True)
