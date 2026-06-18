from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import CategoricalDtype
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from metro_demand_models.configuration import Settings
from metro_demand_models.evaluation.daily import TemporalSplit, slice_split_frame


@dataclass(frozen=True)
class TabularTrainingArtifacts:
    predictions: pd.DataFrame
    fitted_test_pipeline: Pipeline
    feature_columns: list[str]
    transformed_feature_names: list[str]


def train_tabular_model(
    settings: Settings,
    frame: pd.DataFrame,
    splits: list[TemporalSplit],
    *,
    feature_columns: list[str],
) -> TabularTrainingArtifacts:
    missing_columns = set(feature_columns).difference(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Tabular training frame is missing configured feature columns: {missing}.")

    prediction_frames: list[pd.DataFrame] = []
    fitted_test_pipeline: Pipeline | None = None
    transformed_feature_names: list[str] = []

    for split in splits:
        train_frame, score_frame = slice_split_frame(frame, split)
        if train_frame.empty:
            raise ValueError(f"Temporal split '{split.name}' produced an empty training window.")
        if score_frame.empty:
            continue

        pipeline = build_tabular_pipeline(
            settings,
            train_frame,
            feature_columns=feature_columns,
        )
        pipeline.fit(
            train_frame[feature_columns],
            train_frame["trip_count_target"].astype(float),
        )
        required_prediction_columns = [
            "forecast_origin_date",
            "target_date",
            "series_id",
            "linea",
            "estacion",
            "feature_variant",
            "series_policy",
            "horizon_days",
            "trip_count_target",
        ]
        optional_prediction_columns = [
            "series_label",
            "station_abbrev",
        ]
        prediction_columns = required_prediction_columns + [
            column for column in optional_prediction_columns if column in score_frame.columns
        ]
        predictions_frame = score_frame[prediction_columns].copy()
        predictions_frame["variant"] = predictions_frame["feature_variant"]
        predictions_frame["model_name"] = "tabular_hgbr"
        predictions_frame["split_name"] = split.name
        predictions_frame["split_type"] = split.split_type
        predictions_frame["y_true"] = predictions_frame["trip_count_target"]
        predicted_values = np.clip(
            pipeline.predict(score_frame[feature_columns].copy()),
            0.0,
            None,
        )
        predictions_frame["y_pred"] = predicted_values
        prediction_frames.append(predictions_frame)

        if split.split_type == "test":
            fitted_test_pipeline = pipeline
            transformed_feature_names = list(pipeline.named_steps["preprocessor"].get_feature_names_out())

    if fitted_test_pipeline is None:
        raise ValueError("A fitted test pipeline could not be produced.")

    return TabularTrainingArtifacts(
        predictions=pd.concat(prediction_frames, ignore_index=True),
        fitted_test_pipeline=fitted_test_pipeline,
        feature_columns=feature_columns,
        transformed_feature_names=transformed_feature_names,
    )


def build_tabular_pipeline(
    settings: Settings,
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
) -> Pipeline:
    categorical_columns: list[str] = []
    numeric_columns: list[str] = []
    for column in feature_columns:
        series = frame[column]
        if (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(series.dtype, CategoricalDtype)
        ):
            categorical_columns.append(column)
            continue
        numeric_columns.append(column)

    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric_columns:
        transformers.append(("numeric", "passthrough", numeric_columns))
    if categorical_columns:
        categorical_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="constant", fill_value="__missing__")),
                (
                    "encoder",
                    OneHotEncoder(
                        handle_unknown="ignore",
                        sparse_output=False,
                    ),
                ),
            ]
        )
        transformers.append(("categorical", categorical_pipeline, categorical_columns))

    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=False,
    )
    model_settings = settings["daily_modeling"]["model"]["tabular"]
    model = HistGradientBoostingRegressor(
        loss=str(model_settings["loss"]),
        learning_rate=float(model_settings["learning_rate"]),
        max_iter=int(model_settings["max_iter"]),
        max_depth=int(model_settings["max_depth"]),
        min_samples_leaf=int(model_settings["min_samples_leaf"]),
        l2_regularization=float(model_settings["l2_regularization"]),
        max_bins=int(model_settings["max_bins"]),
        early_stopping=bool(model_settings["early_stopping"]),
        random_state=int(settings["daily_modeling"]["random_state"]),
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )
