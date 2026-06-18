from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd

from metro_scenario_studio.domain.schemas import EventVariable, PredictionRow, ScenarioExecution
from metro_scenario_studio.services.artifact_loader import (
    file_sha256,
    load_pickled_model,
    model_artifact_path,
    model_metadata_path,
    read_future_forecast_frame,
    read_historical_predictions_frame,
    read_metrics_summary,
    resolve_training_path,
)
from metro_scenario_studio.services.result_builder import (
    _as_float,
    _first_float,
    _value,
    deterministic_prediction,
    rows_from_frame,
)

if TYPE_CHECKING:
    from metro_scenario_studio.core.config import Settings

logger = logging.getLogger(__name__)


class PredictionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._diagnostics: list[str] = []

    def predict(self, execution: ScenarioExecution) -> list[PredictionRow]:
        self._diagnostics = []
        if self.settings.use_mock_inference:
            logger.info("Using mock deterministic predictions.")
            return deterministic_prediction(execution, self.settings)
        return self._read_model_predictions(execution)

    def diagnostics(self) -> list[str]:
        return list(dict.fromkeys(self._diagnostics))

    def model_registry_snapshot(self) -> dict[str, object]:
        metrics_dir = self.settings.metro_demand_models_root / "artifacts" / "daily_modeling" / "metrics"
        model_path = (
            self.settings.metro_demand_models_root
            / "artifacts"
            / "models"
            / "daily_modeling"
            / "tabular_hgbr__strict_available__all_series__h1.pkl"
        )
        return {
            "promoted_model": {
                "model_name": "tabular_hgbr",
                "primary_variant": "strict_available",
                "scenario_variant": "forecastable_scenario",
                "series_policy": "all_series",
                "model_artifact": str(model_path),
                "model_artifact_exists": model_path.exists(),
                "metrics_dir": str(metrics_dir),
                "future_forecast_config": str(
                    self.settings.metro_demand_models_root
                    / "artifacts"
                    / "daily_modeling"
                    / "future_forecasts"
                    / "future_forecast_config.json"
                ),
            },
            "baselines": ["baseline_naive_simple", "baseline_naive_seasonal_weekly"],
            "metrics": read_metrics_summary(self.settings),
            "notes": [
                "La plataforma lee artefactos del repositorio de modelos en modo solo lectura.",
                "Los escenarios what-if no se presentan como causalidad.",
                "El forecast futuro largo del repositorio de modelos se genero con recursion de predicciones como historial; debe interpretarse con cautela fuera de D+1/D+7.",
            ],
        }

    def _read_model_predictions(self, execution: ScenarioExecution) -> list[PredictionRow]:
        rows: list[PredictionRow] = []
        seen: set[tuple[date, str]] = set()
        sources = (
            (
                ("model_inference", self._run_pickled_model_inference(execution)),
                ("historical", self._read_historical_model_predictions(execution)),
                ("precomputed_future_forecast", self._read_future_forecast(execution)),
            )
            if _should_recompute_scenario(execution)
            else (
                ("historical", self._read_historical_model_predictions(execution)),
                ("model_inference", self._run_pickled_model_inference(execution)),
                ("precomputed_future_forecast", self._read_future_forecast(execution)),
            )
        )
        for source, candidate_rows in sources:
            added_count = 0
            for row in candidate_rows:
                key = (row.target_date, row.series_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
                added_count += 1
            if source == "precomputed_future_forecast" and added_count:
                self._diagnostics.append("precomputed_forecast_fallback_used")
        return sorted(rows, key=lambda item: (item.target_date, item.network_order, item.series_id))

    def _run_pickled_model_inference(self, execution: ScenarioExecution) -> list[PredictionRow]:
        metadata_path = model_metadata_path(self.settings, execution.model_variant, horizon_days=1)
        model_path = model_artifact_path(self.settings, execution.model_variant, horizon_days=1)
        if not metadata_path.exists():
            self._diagnostics.extend(["model_inference_unavailable", "model_metadata_missing"])
            logger.warning(f"Model metadata missing at: {metadata_path}")
            return []
        if not model_path.exists():
            self._diagnostics.extend(["model_inference_unavailable", "model_artifact_missing"])
            logger.warning(f"Model artifact missing at: {model_path}")
            return []
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            feature_columns = [str(column) for column in metadata["feature_columns"]]
            model = load_pickled_model(model_path)
            feature_rows, row_context = self._build_model_inference_rows(
                execution, metadata=metadata, feature_columns=feature_columns
            )
            if feature_rows.empty:
                return []
            predictions = model.predict(feature_rows[feature_columns])
        except Exception as exc:
            self._diagnostics.extend(["model_inference_unavailable", f"model_inference_failed:{type(exc).__name__}"])
            logger.error(f"Pickled model inference failed: {exc}", exc_info=True)
            return []

        model_sha = file_sha256(model_path)
        rows: list[PredictionRow] = []
        for context, y_pred in zip(row_context, predictions, strict=False):
            y_pred_float = _as_float(y_pred)
            if y_pred_float is None:
                continue
            rows.append(
                PredictionRow(
                    target_date=context["target_date"],
                    linea=str(context["linea"]),
                    estacion=str(context["estacion"]),
                    series_id=str(context["series_id"]),
                    station_abbrev=str(context["station_abbrev"]),
                    network_order=int(context["network_order"]),
                    y_pred=round(y_pred_float, 6),
                    y_real=context["y_real"],
                    model_variant=execution.model_variant,
                    horizon_days=1,
                    forecast_origin_date=context["forecast_origin_date"],
                    prediction_mode="model_inference",
                    model_artifact=str(model_path),
                    model_artifact_sha256=model_sha,
                    feature_row_hash=context["feature_row_hash"],
                )
            )
        return rows

    def _build_model_inference_rows(
        self,
        execution: ScenarioExecution,
        *,
        metadata: dict[str, Any],
        feature_columns: list[str],
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        feature_rows, row_context = self._build_future_forecast_feature_rows(
            execution,
            feature_columns=feature_columns,
        )
        seen_keys = {(context["target_date"], str(context["series_id"])) for context in row_context}
        training_path = resolve_training_path(self.settings, metadata, execution.model_variant, horizon_days=1)
        if training_path.exists():
            training_frame = pd.read_parquet(training_path)
            fallback_rows, fallback_context = self._build_inference_feature_rows(
                execution,
                training_frame,
                feature_columns=feature_columns,
                horizon_days=1,
                excluded_keys=seen_keys,
                exclude_precomputed_dates=not _should_recompute_scenario(execution),
            )
            if not fallback_rows.empty:
                feature_rows = pd.concat([feature_rows, fallback_rows], ignore_index=True)
                row_context = [*row_context, *fallback_context]
        return feature_rows, row_context

    def _build_future_forecast_feature_rows(
        self,
        execution: ScenarioExecution,
        *,
        feature_columns: list[str],
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        frame = read_future_forecast_frame(self.settings)
        if frame.empty:
            return pd.DataFrame(columns=feature_columns), []
        missing_features = [column for column in feature_columns if column not in frame.columns]
        if missing_features:
            return pd.DataFrame(columns=feature_columns), []
        frame = frame.copy()
        frame["target_date"] = pd.to_datetime(frame["target_date"], errors="coerce").dt.date
        frame = frame[(frame["target_date"] >= execution.range_start) & (frame["target_date"] <= execution.range_end)]
        if "model_variant" in frame.columns:
            frame = frame[frame["model_variant"].astype(str) == execution.model_variant]
        elif "variant" in frame.columns:
            frame = frame[frame["variant"].astype(str) == execution.model_variant]
        if frame.empty:
            return pd.DataFrame(columns=feature_columns), []
        if "forecast_origin_date" in frame.columns:
            frame["forecast_origin_date"] = pd.to_datetime(frame["forecast_origin_date"], errors="coerce").dt.date

        self._warn_if_recursive_future_features_exceed_horizon(frame)

        feature_rows: list[dict[str, Any]] = []
        contexts: list[dict[str, Any]] = []
        for raw in frame.to_dict(orient="records"):
            feature_row = {column: _normalize_feature_value(raw.get(column)) for column in feature_columns}
            target_date_value = raw["target_date"]
            forecast_origin_date = raw.get("forecast_origin_date")
            feature_row.update(self._scenario_calendar_features(execution, target_date_value))
            feature_row.update(self._scenario_weather_features(execution, target_date_value))
            feature_row.update(self._scenario_event_features(execution, raw, target_date_value))
            feature_row = {column: _normalize_feature_value(feature_row.get(column)) for column in feature_columns}
            contexts.append(
                {
                    "target_date": target_date_value,
                    "forecast_origin_date": forecast_origin_date if isinstance(forecast_origin_date, date) else None,
                    "series_id": str(_value(raw, "series_id", "")),
                    "linea": _value(raw, "linea", ""),
                    "estacion": _value(raw, "estacion", _value(raw, "series_label", "")),
                    "station_abbrev": _value(raw, "station_abbrev", _value(raw, "series_label", "")),
                    "network_order": int(_as_float(_value(raw, "network_order", 0)) or 0),
                    "y_real": _first_float(raw, ["y_true", "trip_count_target"]),
                    "feature_row_hash": _feature_hash(feature_row),
                }
            )
            feature_rows.append(feature_row)
        return pd.DataFrame(feature_rows), contexts

    def _warn_if_recursive_future_features_exceed_horizon(self, frame: pd.DataFrame) -> None:
        if frame.empty or "forecast_origin_date" not in frame.columns:
            return
        target_dates = sorted({value for value in frame["target_date"] if isinstance(value, date)})
        if not target_dates:
            return
        span_days = (target_dates[-1] - target_dates[0]).days + 1
        if span_days <= self.settings.reasonable_horizon_days:
            return
        origin_lags = []
        for raw in frame[["target_date", "forecast_origin_date"]].dropna().to_dict(orient="records"):
            target_date_value = raw["target_date"]
            origin_date_value = raw["forecast_origin_date"]
            if isinstance(target_date_value, date) and isinstance(origin_date_value, date):
                origin_lags.append((target_date_value - origin_date_value).days)
        if origin_lags and min(origin_lags) <= 1:
            self._diagnostics.append("recursive_future_inference_horizon_exceeded")

    def _build_inference_feature_rows(
        self,
        execution: ScenarioExecution,
        training_frame: pd.DataFrame,
        *,
        feature_columns: list[str],
        horizon_days: int,
        excluded_keys: set[tuple[date, str]] | None = None,
        exclude_precomputed_dates: bool = True,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        frame = training_frame.copy()
        for column in ["forecast_origin_date", "target_date"]:
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
        frame = frame.sort_values(["target_date", "series_id"])
        series_latest = frame.dropna(subset=["series_id"]).groupby("series_id", as_index=False).tail(1)
        observed_history = self._observed_history(frame)
        requested_dates = [
            execution.range_start + timedelta(days=offset)
            for offset in range((execution.range_end - execution.range_start).days + 1)
        ]
        existing_prediction_dates = {row.target_date for row in self._read_historical_model_predictions(execution)} | {
            row.target_date for row in self._read_future_forecast(execution)
        }
        inference_dates = (
            [value for value in requested_dates if value not in existing_prediction_dates]
            if exclude_precomputed_dates
            else requested_dates
        )
        if not inference_dates:
            return pd.DataFrame(columns=feature_columns), []

        feature_rows: list[dict[str, Any]] = []
        contexts: list[dict[str, Any]] = []
        for target_date_value in inference_dates:
            forecast_origin_date = target_date_value - timedelta(days=horizon_days)
            for raw in series_latest.to_dict(orient="records"):
                series_id = str(raw["series_id"])
                if excluded_keys and (target_date_value, series_id) in excluded_keys:
                    continue
                feature_row = self._base_feature_row(raw, feature_columns)
                feature_row.update(self._scenario_calendar_features(execution, target_date_value))
                feature_row.update(self._target_history_features(observed_history, series_id, forecast_origin_date))
                feature_row.update(self._scenario_weather_features(execution, target_date_value))
                feature_row.update(self._scenario_event_features(execution, raw, target_date_value))
                feature_row = {column: _normalize_feature_value(feature_row.get(column)) for column in feature_columns}
                context = {
                    "target_date": target_date_value,
                    "forecast_origin_date": forecast_origin_date,
                    "series_id": series_id,
                    "linea": _value(raw, "linea", ""),
                    "estacion": _value(raw, "estacion", _value(raw, "series_label", series_id)),
                    "station_abbrev": _value(raw, "station_abbrev", series_id),
                    "network_order": int(_as_float(_value(raw, "network_order", 0)) or 0),
                    "y_real": self._real_value_for_target(observed_history, series_id, target_date_value),
                    "feature_row_hash": _feature_hash(feature_row),
                }
                feature_rows.append(feature_row)
                contexts.append(context)
        return pd.DataFrame(feature_rows), contexts

    def _observed_history(self, frame: pd.DataFrame) -> pd.DataFrame:
        if "trip_count_target" not in frame.columns:
            return pd.DataFrame(columns=["series_id", "observed_date", "observed_target_value"])
        history = frame.loc[
            frame["trip_count_target"].notna(),
            ["series_id", "target_date", "trip_count_target"],
        ].copy()
        history = history.rename(
            columns={
                "target_date": "observed_date",
                "trip_count_target": "observed_target_value",
            }
        )
        return history.drop_duplicates(["series_id", "observed_date"], keep="last").sort_values(
            ["series_id", "observed_date"]
        )

    def _base_feature_row(self, raw: dict[str, Any], feature_columns: list[str]) -> dict[str, Any]:
        return {column: raw.get(column) for column in feature_columns if column in raw}

    def _target_history_features(
        self,
        observed_history: pd.DataFrame,
        series_id: str,
        forecast_origin_date: date,
    ) -> dict[str, Any]:
        series_history = observed_history.loc[
            (observed_history["series_id"].astype(str) == series_id)
            & (observed_history["observed_date"] <= forecast_origin_date)
        ].sort_values("observed_date")
        features: dict[str, Any] = {
            "target_latest_observed_value": float("nan"),
            "target_days_since_latest_observation": float("nan"),
        }
        if not series_history.empty:
            latest = series_history.iloc[-1]
            features["target_latest_observed_value"] = float(latest["observed_target_value"])
            features["target_days_since_latest_observation"] = (forecast_origin_date - latest["observed_date"]).days
        for lag in [1, 7, 14, 28]:
            lag_date = forecast_origin_date - timedelta(days=lag)
            lag_rows = series_history.loc[series_history["observed_date"] == lag_date]
            features[f"target_lag_{lag}"] = (
                float(lag_rows.iloc[-1]["observed_target_value"]) if not lag_rows.empty else float("nan")
            )
        for window in [7, 28]:
            values = series_history["observed_target_value"].tail(window).astype(float)
            features[f"target_rolling_mean_{window}"] = float(values.mean()) if len(values) else float("nan")
            features[f"target_rolling_std_{window}"] = float(values.std()) if len(values) >= 2 else float("nan")
            features[f"target_observed_count_{window}"] = float(len(values))
        return features

    def _real_value_for_target(
        self,
        observed_history: pd.DataFrame,
        series_id: str,
        target_date_value: date,
    ) -> float | None:
        rows = observed_history.loc[
            (observed_history["series_id"].astype(str) == series_id)
            & (observed_history["observed_date"] == target_date_value)
        ]
        if rows.empty:
            return None
        return _as_float(rows.iloc[-1]["observed_target_value"])

    def _scenario_calendar_features(self, execution: ScenarioExecution, target_date_value: date) -> dict[str, Any]:
        features = _calendar_features(target_date_value)
        calendar = next(
            (item for item in execution.input.calendar_final if item.target_date == target_date_value),
            None,
        )
        if calendar is None:
            return features
        features.update(
            {
                "calendar_day_of_week": calendar.day_of_week,
                "calendar_is_weekend": calendar.day_of_week in {6, 7},
                "calendar_is_holiday": calendar.is_holiday,
                "calendar_holiday_name": calendar.special_day or "",
                "calendar_holiday_scope": "manual_scenario" if calendar.modified else "",
                "calendar_is_preholiday": calendar.is_preholiday,
                "calendar_is_postholiday": calendar.is_postholiday,
                "calendar_is_bridge_candidate": calendar.is_bridge,
            }
        )
        return features

    def _scenario_weather_features(self, execution: ScenarioExecution, target_date_value: date) -> dict[str, Any]:
        weather = next(
            (item for item in execution.input.weather_final if item.target_date == target_date_value),
            None,
        )
        if weather is None:
            return {}
        return {
            "weather_temp_min_c": weather.temp_min,
            "weather_temp_mean_c": weather.temp_mean or weather.approx_temperature,
            "weather_temp_max_c": weather.temp_max,
            "weather_precip_mm": weather.precip_mm,
            "weather_rain_hours": weather.rain_hours,
            "weather_wind_mean_kmh": weather.wind,
            "weather_humidity_mean_pct": weather.humidity,
            "weather_code": weather.weather_code,
            "weather_is_rainy_day": weather.rain,
            "weather_is_heavy_rain_day": weather.heavy_rain,
            "weather_is_hot_day": weather.hot_day,
            "weather_is_cold_day": weather.cold_day,
            "weather_is_bad_weather_day": weather.bad_weather,
        }

    def _scenario_event_features(
        self,
        execution: ScenarioExecution,
        raw_series: dict[str, Any],
        target_date_value: date,
    ) -> dict[str, Any]:
        station_keys = {
            str(_value(raw_series, "series_id", "")),
            str(_value(raw_series, "station_abbrev", "")),
            str(_value(raw_series, "estacion", "")),
        }
        matched_events = []
        for event in execution.input.events_final:
            if event.deleted or not _event_is_active_on(event, target_date_value):
                continue
            affected = {str(value) for value in event.affected_stations}
            if "all" in affected or affected.intersection(station_keys):
                matched_events.append(event)
        high_impact = [event for event in matched_events if event.impact_level.value in {"alto", "muy alto"}]
        unknown_attendance = len(matched_events)
        return {
            "event_active_count": float(len(matched_events)),
            "event_starting_count": float(len(matched_events)),
            "event_ending_count": 0.0,
            "event_starting_estimated_attendance_sum": 0.0,
            "event_starting_unknown_attendance_count": float(unknown_attendance),
            "event_high_impact_starting_count": float(len(high_impact)),
        }

    def _read_historical_model_predictions(self, execution: ScenarioExecution) -> list[PredictionRow]:
        frame = read_historical_predictions_frame(self.settings, execution.model_name, execution.model_variant)
        return rows_from_frame(
            frame, execution, prediction_mode="historical_evaluation_artifact", settings=self.settings
        )

    def _read_future_forecast(self, execution: ScenarioExecution) -> list[PredictionRow]:
        frame = read_future_forecast_frame(self.settings)
        return rows_from_frame(
            frame, execution, prediction_mode="precomputed_forecast_fallback", settings=self.settings
        )


def _calendar_features(target_date_value: date) -> dict[str, Any]:
    iso_week = target_date_value.isocalendar()
    return {
        "calendar_year": target_date_value.year,
        "calendar_month": target_date_value.month,
        "calendar_day": target_date_value.day,
        "calendar_quarter": (target_date_value.month - 1) // 3 + 1,
        "calendar_week_of_year": iso_week.week,
        "calendar_day_of_year": target_date_value.timetuple().tm_yday,
        "calendar_day_of_week": target_date_value.weekday() + 1,
        "calendar_day_of_week_name": target_date_value.strftime("%A"),
        "calendar_is_weekend": target_date_value.weekday() >= 5,
        "calendar_is_holiday": False,
        "calendar_holiday_name": "",
        "calendar_holiday_scope": "",
        "calendar_is_holiday_mmo": False,
        "calendar_is_preholiday": False,
        "calendar_is_postholiday": False,
        "calendar_days_to_next_holiday": float("nan"),
        "calendar_days_since_prev_holiday": float("nan"),
        "calendar_is_bridge_candidate": False,
        "calendar_is_month_start": target_date_value.day == 1,
        "calendar_is_month_end": (target_date_value + timedelta(days=1)).day == 1,
    }


def _normalize_feature_value(value: Any) -> Any:
    if value is None:
        return float("nan")
    if pd.isna(value):
        return float("nan")
    if isinstance(value, bool):
        return float(value)
    return value


def _feature_hash(feature_row: dict[str, Any]) -> str:
    payload = json.dumps(feature_row, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_is_active_on(event: EventVariable, target_date_value: date) -> bool:
    if event.selected_dates:
        return target_date_value in set(event.selected_dates)
    start_date = event.start_date or event.target_date
    end_date = event.end_date or event.target_date
    return start_date <= target_date_value <= end_date


def _should_recompute_scenario(execution: ScenarioExecution) -> bool:
    if execution.model_variant != "forecastable_scenario":
        return False
    return (
        bool(execution.input.manual_overrides)
        or bool(execution.input.llm_accepted_items)
        or any(item.modified for item in execution.input.calendar_final)
        or any(item.modified or item.source == "manual_scenario" for item in execution.input.events_final)
        or any(item.modified or item.source == "manual_scenario" for item in execution.input.weather_final)
    )
