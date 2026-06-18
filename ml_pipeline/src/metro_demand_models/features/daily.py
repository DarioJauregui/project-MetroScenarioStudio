from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from metro_demand_models.configuration import Settings
from metro_demand_models.data.contracts import load_operational_output_contracts
from metro_demand_models.data.io import read_table
from metro_demand_models.data.modeling import (
    ModelingDataBundle,
    prepare_modeling_base_dataset,
)
from metro_demand_models.utils.stations import (
    build_station_series_label,
    fallback_station_abbrev,
    infer_shared_station_abbreviations,
    normalize_station_abbrev,
)


FUTURE_AVAILABLE = "future_available"
FUTURE_AVAILABLE_IF_SCENARIO = "future_available_if_forecast_or_scenario"
NOT_FUTURE_AVAILABLE = "not_future_available"

SUPPORTED_VARIANTS = {"strict_available", "forecastable_scenario"}
SUPPORTED_SERIES_POLICIES = {"all_series", "sparse_excluded"}
BASELINE_SUPPORT_COLUMNS = [
    "baseline_naive_simple",
    "baseline_naive_simple_reference_date",
    "baseline_naive_seasonal_weekly",
    "baseline_naive_seasonal_reference_date",
    "baseline_seasonal_weekday_mean_4",
    "baseline_seasonal_weekday_mean_4_reference_date",
    "baseline_seasonal_weekday_mean_4_reference_count",
]

AUTOREGRESSIVE_FEATURE_COLUMNS = [
    "target_latest_observed_value",
    "target_days_since_latest_observation",
    "target_lag_1",
    "target_lag_7",
    "target_lag_14",
    "target_lag_28",
    "target_rolling_mean_7",
    "target_rolling_std_7",
    "target_observed_count_7",
    "target_rolling_mean_28",
    "target_rolling_std_28",
    "target_observed_count_28",
]

CALENDAR_RENAME_MAP = {
    "year": "calendar_year",
    "month": "calendar_month",
    "day": "calendar_day",
    "quarter": "calendar_quarter",
    "week_of_year": "calendar_week_of_year",
    "day_of_year": "calendar_day_of_year",
    "day_of_week": "calendar_day_of_week",
    "day_of_week_name": "calendar_day_of_week_name",
    "is_weekend": "calendar_is_weekend",
    "is_holiday": "calendar_is_holiday",
    "holiday_name": "calendar_holiday_name",
    "holiday_scope": "calendar_holiday_scope",
    "is_holiday_mmo": "calendar_is_holiday_mmo",
    "is_preholiday": "calendar_is_preholiday",
    "is_postholiday": "calendar_is_postholiday",
    "days_to_next_holiday": "calendar_days_to_next_holiday",
    "days_since_prev_holiday": "calendar_days_since_prev_holiday",
    "is_bridge_candidate": "calendar_is_bridge_candidate",
    "is_month_start": "calendar_is_month_start",
    "is_month_end": "calendar_is_month_end",
}

WEATHER_RENAME_MAP = {
    "temp_min_c": "weather_temp_min_c",
    "temp_max_c": "weather_temp_max_c",
    "temp_mean_c": "weather_temp_mean_c",
    "precip_mm": "weather_precip_mm",
    "rain_hours": "weather_rain_hours",
    "wind_max_kmh": "weather_wind_max_kmh",
    "wind_mean_kmh": "weather_wind_mean_kmh",
    "humidity_mean_pct": "weather_humidity_mean_pct",
    "pressure_mean_hpa": "weather_pressure_mean_hpa",
    "weather_code": "weather_code",
    "is_rainy_day": "weather_is_rainy_day",
    "is_heavy_rain_day": "weather_is_heavy_rain_day",
    "is_hot_day": "weather_is_hot_day",
    "is_cold_day": "weather_is_cold_day",
    "is_bad_weather_day": "weather_is_bad_weather_day",
}

INCIDENT_COLUMNS = [
    "incident_count",
    "delay_minutes_sum",
    "delay_minutes_max",
    "incident_duration_minutes_sum",
    "incident_duration_minutes_max",
    "delay_incident_count",
    "partial_service_incident_count",
    "line_stop_incident_count",
    "single_track_incident_count",
]


@dataclass(frozen=True)
class DailyModelingFoundation:
    panel: pd.DataFrame
    panel_diagnostics: pd.DataFrame
    feature_catalog: pd.DataFrame
    external_target_features: pd.DataFrame
    observed_history: pd.DataFrame
    services_line_daily: pd.DataFrame
    events_phase2a_series_daily: pd.DataFrame
    incidents_daily: pd.DataFrame


@dataclass(frozen=True)
class DailyTrainingDataset:
    frame: pd.DataFrame
    feature_catalog: pd.DataFrame
    panel_diagnostics: pd.DataFrame
    metadata: dict[str, Any]

    @property
    def feature_columns(self) -> list[str]:
        variant = str(self.metadata["variant"])
        inclusion_column = (
            "included_in_strict_available" if variant == "strict_available" else "included_in_forecastable_scenario"
        )
        catalog = self.feature_catalog[
            (self.feature_catalog["is_model_feature"]) & (self.feature_catalog[inclusion_column])
        ]
        return sorted(catalog["feature_name"].tolist())


def build_daily_modeling_foundation(
    settings: Settings,
    *,
    modeling_bundle: ModelingDataBundle | None = None,
    operational_frames: dict[str, pd.DataFrame] | None = None,
) -> DailyModelingFoundation:
    resolved_bundle = modeling_bundle or prepare_modeling_base_dataset(settings)
    model_base = _prepare_model_base(resolved_bundle.model_base)
    panel = _build_series_panel(model_base)
    panel_diagnostics = build_panel_diagnostics(panel)
    feature_catalog = build_feature_catalog(settings)
    external_target_features = _prepare_external_target_features(resolved_bundle.external_daily_features)
    resolved_operational_frames = operational_frames or _load_operational_frames(settings)
    observed_history = panel.loc[
        panel["observed_target_value"].notna(),
        [
            "series_id",
            "service_date",
            "observed_target_value",
            "current_day_of_week",
        ],
    ].copy()
    observed_history = (
        observed_history.rename(
            columns={
                "service_date": "observed_date",
                "observed_target_value": "observed_target_value",
                "current_day_of_week": "observed_day_of_week",
            }
        )
        .sort_values(["series_id", "observed_date"])
        .reset_index(drop=True)
    )

    return DailyModelingFoundation(
        panel=panel,
        panel_diagnostics=panel_diagnostics,
        feature_catalog=feature_catalog,
        external_target_features=external_target_features,
        observed_history=observed_history,
        services_line_daily=_prepare_services_line_daily(resolved_operational_frames["services_line_daily"]),
        events_phase2a_series_daily=_prepare_events_phase2a_series_daily(
            resolved_operational_frames["events_phase2a_series_daily"]
        ),
        incidents_daily=_prepare_incidents_daily(resolved_operational_frames["incidents_daily"]),
    )


def build_daily_training_dataset(
    settings: Settings,
    variant: str,
    horizon_days: int,
    *,
    series_policy: str = "all_series",
    foundation: DailyModelingFoundation | None = None,
) -> DailyTrainingDataset:
    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(f"Unsupported modeling variant '{variant}'. Expected one of {sorted(SUPPORTED_VARIANTS)}.")
    if series_policy not in SUPPORTED_SERIES_POLICIES:
        raise ValueError(
            f"Unsupported series policy '{series_policy}'. Expected one of {sorted(SUPPORTED_SERIES_POLICIES)}."
        )
    if horizon_days <= 0:
        raise ValueError("The forecast horizon must be a positive integer.")

    resolved_foundation = foundation or build_daily_modeling_foundation(settings)
    frame = resolved_foundation.panel.copy()
    frame = frame.rename(columns={"service_date": "forecast_origin_date"})
    frame["target_date"] = frame["forecast_origin_date"] + pd.to_timedelta(
        horizon_days,
        unit="D",
    )
    frame["horizon_days"] = horizon_days
    frame["feature_variant"] = variant
    frame["series_policy"] = series_policy

    target_lookup = resolved_foundation.panel[["series_id", "service_date", "observed_target_value"]].rename(
        columns={
            "service_date": "target_date",
            "observed_target_value": "trip_count_target",
        }
    )
    frame = frame.merge(
        target_lookup,
        how="left",
        on=["series_id", "target_date"],
        validate="m:1",
    )
    frame = frame.loc[frame["trip_count_target"].notna()].copy()
    frame["target_day_of_week"] = frame["target_date"].dt.dayofweek

    frame = _attach_baseline_support(frame, resolved_foundation.observed_history)
    frame = frame.merge(
        resolved_foundation.external_target_features,
        how="left",
        on="target_date",
        validate="m:1",
    )

    if variant == "forecastable_scenario":
        scenario_start_date = pd.Timestamp(str(settings["daily_modeling"]["scenario_start_date"])).normalize()
        frame = frame.loc[frame["target_date"] >= scenario_start_date].copy()
        frame = _attach_service_features(frame, resolved_foundation.services_line_daily)
        frame = _attach_event_features(
            frame,
            resolved_foundation.events_phase2a_series_daily,
        )

    if series_policy == "sparse_excluded":
        sparse_series_ids = {str(value) for value in settings["daily_modeling"]["sparse_series_ids"]}
        frame = frame.loc[~frame["series_id"].isin(sparse_series_ids)].copy()

    frame = _finalize_training_frame_dtypes(frame)
    feature_columns = _select_variant_feature_columns(
        resolved_foundation.feature_catalog,
        variant,
    )
    keep_columns = [
        "forecast_origin_date",
        "target_date",
        "horizon_days",
        "feature_variant",
        "series_policy",
        "series_id",
        "series_label",
        "linea",
        "estacion",
        "station_abbrev",
        "station_join_key",
        "trip_count_target",
        *feature_columns,
        *BASELINE_SUPPORT_COLUMNS,
    ]
    existing_columns = list(dict.fromkeys(column for column in keep_columns if column in frame.columns))
    frame = frame[existing_columns].sort_values(["forecast_origin_date", "series_id"]).reset_index(drop=True)

    metadata = {
        "variant": variant,
        "series_policy": series_policy,
        "horizon_days": horizon_days,
        "row_count": int(len(frame)),
        "series_count": int(frame["series_id"].nunique()),
        "forecast_origin_min": str(frame["forecast_origin_date"].min().date()),
        "forecast_origin_max": str(frame["forecast_origin_date"].max().date()),
        "target_min": str(frame["target_date"].min().date()),
        "target_max": str(frame["target_date"].max().date()),
        "feature_columns": feature_columns,
    }
    return DailyTrainingDataset(
        frame=frame,
        feature_catalog=resolved_foundation.feature_catalog,
        panel_diagnostics=resolved_foundation.panel_diagnostics,
        metadata=metadata,
    )


def build_panel_diagnostics(panel: pd.DataFrame) -> pd.DataFrame:
    global_start = panel["service_date"].min()
    global_end = panel["service_date"].max()
    diagnostics_rows: list[dict[str, Any]] = []

    for series_id, series_frame in panel.groupby("series_id", sort=True):
        ordered = series_frame.sort_values("service_date").reset_index(drop=True)
        observed_mask = ordered["observed_target_value"].notna()
        first_observed = ordered.loc[observed_mask, "service_date"].min()
        last_observed = ordered.loc[observed_mask, "service_date"].max()
        observed_days = int(observed_mask.sum())
        calendar_span_days = int(len(ordered))
        intra_span_missing_days = int(calendar_span_days - observed_days)
        coverage_ratio = float(observed_days / calendar_span_days) if calendar_span_days else np.nan
        diagnostics_rows.append(
            {
                "series_id": series_id,
                "series_label": ordered["series_label"].iat[0],
                "linea": ordered["linea"].iat[0],
                "estacion": ordered["estacion"].iat[0],
                "station_abbrev": ordered["station_abbrev"].iat[0],
                "station_join_key": ordered["station_join_key"].iat[0],
                "first_observed_date": first_observed,
                "last_observed_date": last_observed,
                "observed_days": observed_days,
                "calendar_span_days": calendar_span_days,
                "pre_observation_days": int((first_observed - global_start).days),
                "post_observation_days": int((global_end - last_observed).days),
                "intra_span_missing_days": intra_span_missing_days,
                "coverage_ratio": coverage_ratio,
                "max_gap_days": _max_missing_gap(observed_mask),
            }
        )

    return pd.DataFrame(diagnostics_rows).sort_values("series_id").reset_index(drop=True)


def build_feature_catalog(settings: Settings) -> pd.DataFrame:
    feature_settings = settings["daily_modeling"]["features"]
    rows: list[dict[str, Any]] = []

    def add_rows(
        feature_names: list[str] | tuple[str, ...],
        *,
        source_dataset: str,
        feature_group: str,
        availability_class: str,
        included_in_strict_available: bool,
        included_in_forecastable_scenario: bool,
        model_dtype: str,
        is_model_feature: bool = True,
        exclusion_reason: str | None = None,
    ) -> None:
        for feature_name in feature_names:
            rows.append(
                {
                    "feature_name": str(feature_name),
                    "source_dataset": source_dataset,
                    "feature_group": feature_group,
                    "availability_class": availability_class,
                    "included_in_strict_available": included_in_strict_available,
                    "included_in_forecastable_scenario": (included_in_forecastable_scenario),
                    "model_dtype": model_dtype,
                    "is_model_feature": is_model_feature,
                    "exclusion_reason": exclusion_reason,
                }
            )

    add_rows(
        list(feature_settings["static_feature_columns"]),
        source_dataset="phase_2a_station_daily_model_base",
        feature_group="static",
        availability_class=FUTURE_AVAILABLE,
        included_in_strict_available=True,
        included_in_forecastable_scenario=True,
        model_dtype="mixed",
    )
    add_rows(
        list(feature_settings["calendar_feature_columns"]),
        source_dataset="external_daily_features",
        feature_group="calendar",
        availability_class=FUTURE_AVAILABLE,
        included_in_strict_available=True,
        included_in_forecastable_scenario=True,
        model_dtype="mixed",
    )
    add_rows(
        AUTOREGRESSIVE_FEATURE_COLUMNS,
        source_dataset="phase_2a_station_daily_model_base",
        feature_group="autoregressive",
        availability_class=FUTURE_AVAILABLE,
        included_in_strict_available=True,
        included_in_forecastable_scenario=True,
        model_dtype="numeric",
    )
    add_rows(
        list(feature_settings["weather_feature_columns"]),
        source_dataset="external_daily_features",
        feature_group="weather",
        availability_class=FUTURE_AVAILABLE_IF_SCENARIO,
        included_in_strict_available=False,
        included_in_forecastable_scenario=True,
        model_dtype="mixed",
    )
    add_rows(
        list(feature_settings["service_feature_columns"]),
        source_dataset="services_line_daily",
        feature_group="planned_service",
        availability_class=FUTURE_AVAILABLE_IF_SCENARIO,
        included_in_strict_available=False,
        included_in_forecastable_scenario=True,
        model_dtype="mixed",
    )
    add_rows(
        list(feature_settings["event_feature_columns"]),
        source_dataset="events_phase2a_series_daily",
        feature_group="planned_events",
        availability_class=FUTURE_AVAILABLE_IF_SCENARIO,
        included_in_strict_available=False,
        included_in_forecastable_scenario=True,
        model_dtype="numeric",
    )
    add_rows(
        BASELINE_SUPPORT_COLUMNS,
        source_dataset="phase_2a_station_daily_model_base",
        feature_group="baseline_support",
        availability_class=FUTURE_AVAILABLE,
        included_in_strict_available=False,
        included_in_forecastable_scenario=False,
        model_dtype="mixed",
        is_model_feature=False,
        exclusion_reason="baseline_support_only",
    )
    add_rows(
        INCIDENT_COLUMNS,
        source_dataset="incidents_daily",
        feature_group="observed_operations",
        availability_class=NOT_FUTURE_AVAILABLE,
        included_in_strict_available=False,
        included_in_forecastable_scenario=False,
        model_dtype="numeric",
        exclusion_reason="realized_operations_not_available_at_prediction_time",
    )
    add_rows(
        ["used_service_xml_name"],
        source_dataset="services_line_daily",
        feature_group="observed_operations",
        availability_class=NOT_FUTURE_AVAILABLE,
        included_in_strict_available=False,
        included_in_forecastable_scenario=False,
        model_dtype="categorical",
        exclusion_reason="real_service_execution_is_not_available_in_future",
    )
    add_rows(
        list(feature_settings["excluded_external_event_columns"]),
        source_dataset="external_daily_features",
        feature_group="excluded_duplicate_event_signal",
        availability_class=FUTURE_AVAILABLE_IF_SCENARIO,
        included_in_strict_available=False,
        included_in_forecastable_scenario=False,
        model_dtype="numeric",
        exclusion_reason="excluded_to_avoid_double_count_with_events_phase2a_series_daily",
    )
    add_rows(
        list(feature_settings["excluded_master_leakage_columns"]),
        source_dataset="master_datasets",
        feature_group="excluded_leakage",
        availability_class=NOT_FUTURE_AVAILABLE,
        included_in_strict_available=False,
        included_in_forecastable_scenario=False,
        model_dtype="mixed",
        exclusion_reason="historical_accumulator_or_non_operational_tracing_field",
    )

    return pd.DataFrame(rows).sort_values("feature_name").reset_index(drop=True)


def _prepare_model_base(model_base: pd.DataFrame) -> pd.DataFrame:
    frame = model_base.copy()
    frame["service_date"] = pd.to_datetime(frame["service_date"]).dt.normalize()
    if "station_abbrev" not in frame.columns:
        frame["station_abbrev"] = frame["station_join_key"].map(lambda value: fallback_station_abbrev(value))
    frame["station_abbrev"] = frame["station_abbrev"].map(normalize_station_abbrev)
    return frame


def _build_series_panel(model_base: pd.DataFrame) -> pd.DataFrame:
    series_metadata = (
        model_base.sort_values(["series_id", "service_date"])
        .groupby("series_id", as_index=False)
        .agg(
            linea=("linea", "first"),
            estacion=("estacion", "first"),
            station_join_key=("station_join_key", "first"),
            station_abbrev=("station_abbrev", "first"),
            zone=("zone", "first"),
            station_group=("station_group", "first"),
            network_order=("network_order", "first"),
            is_interchange_candidate=("is_interchange_candidate", "first"),
            first_observed_date=("service_date", "min"),
            last_observed_date=("service_date", "max"),
        )
    )

    panel_frames: list[pd.DataFrame] = []
    metadata_columns = [
        "series_id",
        "linea",
        "estacion",
        "station_join_key",
        "station_abbrev",
        "zone",
        "station_group",
        "network_order",
        "is_interchange_candidate",
    ]
    for row in series_metadata.itertuples(index=False):
        series_dates = pd.date_range(row.first_observed_date, row.last_observed_date, freq="D")
        panel_frame = pd.DataFrame({"service_date": series_dates})
        for column in metadata_columns:
            panel_frame[column] = getattr(row, column)
        panel_frames.append(panel_frame)

    panel = pd.concat(panel_frames, ignore_index=True)
    observed_targets = model_base[["series_id", "service_date", "trip_count"]].rename(
        columns={"trip_count": "observed_target_value"}
    )
    panel = panel.merge(
        observed_targets,
        how="left",
        on=["series_id", "service_date"],
        validate="1:1",
    )
    shared_station_abbreviations = infer_shared_station_abbreviations(series_metadata)
    panel["series_label"] = panel.apply(
        lambda row: build_series_label(
            linea=str(row["linea"]),
            station_abbrev=str(row["station_abbrev"]),
            shared_station_abbreviations=shared_station_abbreviations,
        ),
        axis=1,
    )
    panel["current_day_of_week"] = panel["service_date"].dt.dayofweek
    panel["is_observed_target"] = panel["observed_target_value"].notna()

    observed_date = panel["service_date"].where(panel["is_observed_target"])
    panel["latest_observed_date"] = observed_date.groupby(panel["series_id"]).ffill()
    panel["target_latest_observed_value"] = panel.groupby("series_id")["observed_target_value"].ffill()
    panel["target_days_since_latest_observation"] = (
        panel["service_date"] - panel["latest_observed_date"]
    ).dt.days.astype("float64")

    grouped_target = panel.groupby("series_id")["observed_target_value"]
    for lag in [1, 7, 14, 28]:
        panel[f"target_lag_{lag}"] = grouped_target.shift(lag)

    for window in [7, 28]:
        panel[f"target_rolling_mean_{window}"] = grouped_target.transform(
            lambda values: values.rolling(window=window, min_periods=1).mean()
        )
        panel[f"target_rolling_std_{window}"] = grouped_target.transform(
            lambda values: values.rolling(window=window, min_periods=2).std()
        )
        panel[f"target_observed_count_{window}"] = grouped_target.transform(
            lambda values: values.rolling(window=window, min_periods=1).count()
        )

    return panel.sort_values(["service_date", "series_id"]).reset_index(drop=True)


def build_series_label(
    *,
    linea: str,
    station_abbrev: str,
    shared_station_abbreviations: set[str] | None = None,
) -> str:
    return build_station_series_label(
        linea=linea,
        station_abbrev=station_abbrev,
        shared_station_abbreviations=shared_station_abbreviations,
    )


def _prepare_external_target_features(
    external_daily_features: pd.DataFrame,
) -> pd.DataFrame:
    frame = external_daily_features.copy()
    frame["target_date"] = pd.to_datetime(frame["date"]).dt.normalize()
    selected_columns = [
        "target_date",
        *CALENDAR_RENAME_MAP.keys(),
        *WEATHER_RENAME_MAP.keys(),
    ]
    frame = frame[selected_columns].rename(
        columns={
            **CALENDAR_RENAME_MAP,
            **WEATHER_RENAME_MAP,
        }
    )
    return frame.sort_values("target_date").reset_index(drop=True)


def _prepare_services_line_daily(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    frame["target_date"] = pd.to_datetime(frame["service_date"]).dt.normalize()
    if "used_service_xml_name" not in frame.columns:
        frame["used_service_xml_name"] = pd.NA
    frame["service_planned_start_minutes"] = frame["commercial_start_minutes"]
    frame["service_line_end_minutes"] = frame["line_end_minutes"]
    frame["service_line_end_day_offset"] = frame["line_end_day_offset"]
    frame["service_duration_minutes"] = frame["line_end_minutes"] - frame["commercial_start_minutes"]
    frame["service_has_planned_xml"] = frame["planned_service_xml_name"].notna()
    frame["service_planned_code"] = frame["planned_service_xml_name"].fillna(frame["service_name_raw"])
    return (
        frame[
            [
                "target_date",
                "linea",
                "service_planned_start_minutes",
                "service_line_end_minutes",
                "service_line_end_day_offset",
                "service_duration_minutes",
                "service_has_planned_xml",
                "service_planned_code",
                "used_service_xml_name",
            ]
        ]
        .sort_values(["target_date", "linea"])
        .reset_index(drop=True)
    )


def _prepare_events_phase2a_series_daily(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    frame["target_date"] = pd.to_datetime(frame["service_date"]).dt.normalize()
    frame["event_active_count"] = frame["active_event_count_deduplicated"]
    frame["event_starting_count"] = frame["starting_event_count_deduplicated"]
    frame["event_ending_count"] = frame["ending_event_count_deduplicated"]
    frame["event_starting_estimated_attendance_sum"] = frame["starting_estimated_attendance_sum_deduplicated"]
    frame["event_starting_unknown_attendance_count"] = frame["starting_unknown_attendance_count_deduplicated"]
    frame["event_high_impact_starting_count"] = frame["high_impact_starting_event_count_deduplicated"]
    return (
        frame[
            [
                "target_date",
                "linea",
                "estacion",
                "event_active_count",
                "event_starting_count",
                "event_ending_count",
                "event_starting_estimated_attendance_sum",
                "event_starting_unknown_attendance_count",
                "event_high_impact_starting_count",
            ]
        ]
        .sort_values(["target_date", "linea", "estacion"])
        .reset_index(drop=True)
    )


def _prepare_incidents_daily(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    frame["target_date"] = pd.to_datetime(frame["service_date"]).dt.normalize()
    return frame.sort_values(["target_date", "impact_scope"]).reset_index(drop=True)


def _attach_baseline_support(
    frame: pd.DataFrame,
    observed_history: pd.DataFrame,
) -> pd.DataFrame:
    enriched = frame.copy().reset_index(drop=True)
    enriched["_row_id"] = np.arange(len(enriched))
    enriched["baseline_naive_simple"] = enriched["target_latest_observed_value"]
    latest_reference = enriched["forecast_origin_date"] - pd.to_timedelta(
        enriched["target_days_since_latest_observation"],
        unit="D",
    )
    enriched["baseline_naive_simple_reference_date"] = latest_reference.where(enriched["baseline_naive_simple"].notna())

    seasonal_parts: list[pd.DataFrame] = []
    history = observed_history.sort_values(["series_id", "observed_date"]).reset_index(drop=True)
    history["baseline_seasonal_weekday_mean_4"] = history.groupby(["series_id", "observed_day_of_week"])[
        "observed_target_value"
    ].transform(lambda values: values.rolling(window=4, min_periods=1).mean())
    history["baseline_seasonal_weekday_mean_4_reference_count"] = history.groupby(
        ["series_id", "observed_day_of_week"]
    )["observed_target_value"].transform(lambda values: values.rolling(window=4, min_periods=1).count())
    for target_weekday in range(7):
        subset = enriched.loc[enriched["target_day_of_week"] == target_weekday].copy()
        if subset.empty:
            continue
        weekday_history = history.loc[
            history["observed_day_of_week"] == target_weekday,
            [
                "series_id",
                "observed_date",
                "observed_target_value",
                "baseline_seasonal_weekday_mean_4",
                "baseline_seasonal_weekday_mean_4_reference_count",
            ],
        ].copy()
        if weekday_history.empty:
            subset["baseline_naive_seasonal_weekly"] = np.nan
            subset["baseline_naive_seasonal_reference_date"] = pd.NaT
            subset["baseline_seasonal_weekday_mean_4"] = np.nan
            subset["baseline_seasonal_weekday_mean_4_reference_date"] = pd.NaT
            subset["baseline_seasonal_weekday_mean_4_reference_count"] = np.nan
            seasonal_parts.append(subset)
            continue
        for series_id, series_subset in subset.groupby("series_id", sort=False):
            series_history = weekday_history.loc[
                weekday_history["series_id"] == series_id,
                [
                    "observed_date",
                    "observed_target_value",
                    "baseline_seasonal_weekday_mean_4",
                    "baseline_seasonal_weekday_mean_4_reference_count",
                ],
            ].copy()
            if series_history.empty:
                series_subset["baseline_naive_seasonal_weekly"] = np.nan
                series_subset["baseline_naive_seasonal_reference_date"] = pd.NaT
                series_subset["baseline_seasonal_weekday_mean_4"] = np.nan
                series_subset["baseline_seasonal_weekday_mean_4_reference_date"] = pd.NaT
                series_subset["baseline_seasonal_weekday_mean_4_reference_count"] = np.nan
                seasonal_parts.append(series_subset)
                continue
            merged = pd.merge_asof(
                series_subset.sort_values("forecast_origin_date"),
                series_history.rename(
                    columns={
                        "observed_date": "baseline_naive_seasonal_reference_date",
                        "observed_target_value": "baseline_naive_seasonal_weekly",
                    }
                ).sort_values("baseline_naive_seasonal_reference_date"),
                left_on="forecast_origin_date",
                right_on="baseline_naive_seasonal_reference_date",
                direction="backward",
            )
            merged["baseline_seasonal_weekday_mean_4_reference_date"] = merged["baseline_naive_seasonal_reference_date"]
            seasonal_parts.append(merged)

    seasonal_frame = pd.concat(seasonal_parts, ignore_index=True)
    seasonal_frame = seasonal_frame.sort_values("_row_id").drop(columns=["_row_id"])
    return seasonal_frame.reset_index(drop=True)


def _attach_service_features(
    frame: pd.DataFrame,
    services_line_daily: pd.DataFrame,
) -> pd.DataFrame:
    merged = frame.merge(
        services_line_daily,
        how="left",
        on=["target_date", "linea"],
        validate="m:1",
    )
    merged["service_has_planned_xml"] = merged["service_has_planned_xml"].astype("boolean").fillna(False)
    return merged


def _attach_event_features(
    frame: pd.DataFrame,
    events_phase2a_series_daily: pd.DataFrame,
) -> pd.DataFrame:
    merged = frame.merge(
        events_phase2a_series_daily,
        how="left",
        on=["target_date", "linea", "estacion"],
        validate="m:1",
    )
    event_columns = [
        "event_active_count",
        "event_starting_count",
        "event_ending_count",
        "event_starting_estimated_attendance_sum",
        "event_starting_unknown_attendance_count",
        "event_high_impact_starting_count",
    ]
    for column in event_columns:
        merged[column] = merged[column].fillna(0.0)
    return merged


def _finalize_training_frame_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    finalized = frame.copy()
    bool_like_columns = [
        "is_interchange_candidate",
        "calendar_is_weekend",
        "calendar_is_holiday",
        "calendar_is_holiday_mmo",
        "calendar_is_preholiday",
        "calendar_is_postholiday",
        "calendar_is_bridge_candidate",
        "calendar_is_month_start",
        "calendar_is_month_end",
        "weather_is_rainy_day",
        "weather_is_heavy_rain_day",
        "weather_is_hot_day",
        "weather_is_cold_day",
        "weather_is_bad_weather_day",
        "service_has_planned_xml",
    ]
    for column in bool_like_columns:
        if column in finalized.columns:
            finalized[column] = finalized[column].astype("float64")

    categorical_columns = [
        "series_id",
        "linea",
        "zone",
        "station_group",
        "calendar_day_of_week_name",
        "calendar_holiday_name",
        "calendar_holiday_scope",
        "weather_code",
        "service_planned_code",
    ]
    for column in categorical_columns:
        if column in finalized.columns:
            finalized[column] = finalized[column].astype("object")

    return finalized


def _select_variant_feature_columns(
    feature_catalog: pd.DataFrame,
    variant: str,
) -> list[str]:
    inclusion_column = (
        "included_in_strict_available" if variant == "strict_available" else "included_in_forecastable_scenario"
    )
    return sorted(
        feature_catalog.loc[
            feature_catalog["is_model_feature"] & feature_catalog[inclusion_column],
            "feature_name",
        ].tolist()
    )


def _load_operational_frames(settings: Settings) -> dict[str, pd.DataFrame]:
    contracts = load_operational_output_contracts(settings)
    loaded: dict[str, pd.DataFrame] = {}
    for name in [
        "services_line_daily",
        "events_phase2a_series_daily",
        "incidents_daily",
    ]:
        contract = contracts[name]
        file_path = _resolve_operational_output_path(settings, contract.resolve_path(settings), name)
        loaded[name] = read_table(file_path)
    return loaded


def _resolve_operational_output_path(
    settings: Settings,
    directory: Path,
    dataset_name: str,
) -> Path:
    parquet_path = directory / f"{dataset_name}.parquet"
    if parquet_path.exists():
        return parquet_path
    csv_path = directory / f"{dataset_name}.csv"
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(
        f"Operational dataset '{dataset_name}' was not found under '{directory}'. "
        "Run scripts/build_operational_datasets.py first."
    )


def _max_missing_gap(observed_mask: pd.Series) -> int:
    missing = (~observed_mask).astype(int).to_numpy()
    max_gap = 0
    current_gap = 0
    for value in missing:
        if value:
            current_gap += 1
            max_gap = max(max_gap, current_gap)
        else:
            current_gap = 0
    return int(max_gap)
