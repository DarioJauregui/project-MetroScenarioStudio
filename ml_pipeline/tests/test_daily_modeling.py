from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from metro_demand_models.data.modeling import ModelingDataBundle
from metro_demand_models.evaluation.daily import (
    build_temporal_splits,
    evaluate_forecasts,
    select_recommended_series_policy,
)
from metro_demand_models.features.daily import (
    CALENDAR_RENAME_MAP,
    WEATHER_RENAME_MAP,
    build_daily_modeling_foundation,
    build_daily_training_dataset,
)
from metro_demand_models.models.baselines import run_baselines
from metro_demand_models.models.tabular import train_tabular_model
from metro_demand_models.training.daily import log_experiment_run, save_experiment_outputs


def test_daily_training_dataset_preserves_gaps_and_variant_boundaries(
    tmp_path: Path,
) -> None:
    settings = _build_test_settings(tmp_path)
    bundle = _build_modeling_bundle()
    operational_frames = _build_operational_frames()

    foundation = build_daily_modeling_foundation(
        settings,
        modeling_bundle=bundle,
        operational_frames=operational_frames,
    )
    gap_row = foundation.panel.loc[
        (foundation.panel["series_id"] == "ALP") & (foundation.panel["service_date"] == pd.Timestamp("2024-04-10"))
    ].iloc[0]
    assert pd.isna(gap_row["observed_target_value"])
    sparse_row = foundation.panel_diagnostics.loc[foundation.panel_diagnostics["series_id"] == "GDL2"].iloc[0]
    assert int(sparse_row["intra_span_missing_days"]) > 100
    assert sparse_row["series_label"] == "GDL2"

    strict_dataset = build_daily_training_dataset(
        settings,
        "strict_available",
        1,
        foundation=foundation,
    )
    scenario_dataset = build_daily_training_dataset(
        settings,
        "forecastable_scenario",
        7,
        foundation=foundation,
    )
    sparse_excluded_dataset = build_daily_training_dataset(
        settings,
        "strict_available",
        1,
        series_policy="sparse_excluded",
        foundation=foundation,
    )

    assert "weather_temp_mean_c" not in strict_dataset.frame.columns
    assert "weather_temp_mean_c" in scenario_dataset.frame.columns
    assert "event_active_count" in scenario_dataset.frame.columns
    assert "station_abbrev" in strict_dataset.frame.columns
    assert "series_label" in strict_dataset.frame.columns
    assert "baseline_seasonal_weekday_mean_4" in strict_dataset.frame.columns
    assert scenario_dataset.frame["target_date"].min() >= pd.Timestamp("2024-03-08")
    assert "GDL2" not in sparse_excluded_dataset.frame["series_id"].unique()
    assert strict_dataset.frame["trip_count_target"].notna().all()


def test_temporal_splits_baselines_tabular_and_mlflow_smoke(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    foundation = build_daily_modeling_foundation(
        settings,
        modeling_bundle=_build_modeling_bundle(),
        operational_frames=_build_operational_frames(),
    )
    dataset = build_daily_training_dataset(
        settings,
        "strict_available",
        1,
        foundation=foundation,
    )

    splits = build_temporal_splits(settings, dataset.frame)
    assert len(splits) == 4
    assert all(split.train_end < split.score_start for split in splits)
    assert splits[-1].split_type == "test"

    baseline_predictions = run_baselines(dataset.frame, splits)
    baseline_evaluation = evaluate_forecasts(baseline_predictions)
    assert set(baseline_predictions["model_name"]) == {
        "baseline_naive_simple",
        "baseline_naive_seasonal_weekly",
    }
    assert not baseline_evaluation.split_metrics.empty

    tabular_artifacts = train_tabular_model(
        settings,
        dataset.frame,
        splits,
        feature_columns=list(dataset.metadata["feature_columns"]),
    )
    assert (tabular_artifacts.predictions["y_pred"] >= 0).all()
    tabular_evaluation = evaluate_forecasts(tabular_artifacts.predictions)
    assert not tabular_evaluation.split_metrics.empty

    artifact_paths = save_experiment_outputs(
        settings,
        model_name="tabular_hgbr",
        variant="strict_available",
        series_policy="all_series",
        horizon_days=1,
        predictions=tabular_artifacts.predictions,
        evaluation=tabular_evaluation,
        feature_catalog=dataset.feature_catalog,
        selected_feature_columns=list(dataset.metadata["feature_columns"]),
        metadata=dataset.metadata,
        model_object=tabular_artifacts.fitted_test_pipeline,
    )
    run_name = log_experiment_run(
        settings,
        model_name="tabular_hgbr",
        variant="strict_available",
        series_policy="all_series",
        horizon_days=1,
        feature_catalog=dataset.feature_catalog,
        selected_feature_columns=list(dataset.metadata["feature_columns"]),
        evaluation=tabular_evaluation,
        artifact_paths=artifact_paths,
    )
    assert run_name == "tabular_hgbr__strict_available__all_series__h1"
    assert Path(artifact_paths["predictions"]).exists()
    assert Path(artifact_paths["run_manifest"]).exists()
    run_manifest = json.loads(Path(artifact_paths["run_manifest"]).read_text(encoding="utf-8"))
    assert run_manifest["model"]["model_name"] == "tabular_hgbr"
    assert run_manifest["model"]["variant"] == "strict_available"
    assert run_manifest["tracking"]["mlflow_experiment"] == "daily-modeling-test"
    assert run_manifest["data"]["dataset_path"]
    assert "code_version" in run_manifest
    assert (tmp_path / "mlruns").exists()

    import mlflow

    run_frame = mlflow.search_runs(
        experiment_names=["daily-modeling-test"],
        filter_string=f"tags.mlflow.runName = '{run_name}'",
    )
    assert run_frame["params.model_family"].iloc[0] == "tabular"
    assert run_frame["params.target_transform"].iloc[0] == "none"
    assert "calendar" in run_frame["params.feature_groups"].iloc[0]


def test_series_policy_selection_rule_prefers_sparse_exclusion_only_with_evidence(
    tmp_path: Path,
) -> None:
    settings = _build_test_settings(tmp_path)
    split_metrics = pd.DataFrame(
        [
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "all_series",
                "horizon_days": 1,
                "split_name": "test",
                "split_type": "test",
                "wape": 0.20,
            },
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "sparse_excluded",
                "horizon_days": 1,
                "split_name": "test",
                "split_type": "test",
                "wape": 0.18,
            },
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "all_series",
                "horizon_days": 7,
                "split_name": "test",
                "split_type": "test",
                "wape": 0.25,
            },
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "sparse_excluded",
                "horizon_days": 7,
                "split_name": "test",
                "split_type": "test",
                "wape": 0.24,
            },
        ]
    )
    line_metrics = pd.DataFrame(
        [
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "all_series",
                "horizon_days": 1,
                "split_name": "test",
                "split_type": "test",
                "linea": "LINEA 1",
                "wape": 0.19,
            },
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "sparse_excluded",
                "horizon_days": 1,
                "split_name": "test",
                "split_type": "test",
                "linea": "LINEA 1",
                "wape": 0.188,
            },
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "all_series",
                "horizon_days": 7,
                "split_name": "test",
                "split_type": "test",
                "linea": "LINEA 1",
                "wape": 0.24,
            },
            {
                "model_name": "tabular_hgbr",
                "variant": "strict_available",
                "series_policy": "sparse_excluded",
                "horizon_days": 7,
                "split_name": "test",
                "split_type": "test",
                "linea": "LINEA 1",
                "wape": 0.239,
            },
        ]
    )

    decision = select_recommended_series_policy(settings, split_metrics, line_metrics)
    assert decision["recommended_series_policy"] == "sparse_excluded"


def _build_test_settings(tmp_path: Path) -> dict[str, object]:
    return {
        "runtime": {"project_root": str(tmp_path)},
        "resolved_paths": {
            "daily_training_data_dir": str(tmp_path / "training_data"),
            "daily_modeling_predictions_dir": str(tmp_path / "predictions"),
            "daily_modeling_metrics_dir": str(tmp_path / "metrics"),
            "daily_modeling_models_dir": str(tmp_path / "models"),
            "mlruns_dir": str(tmp_path / "mlruns"),
        },
        "daily_modeling": {
            "forecast_origin_date_column": "forecast_origin_date",
            "available_variants": ["strict_available", "forecastable_scenario"],
            "scenario_start_date": "2024-03-08",
            "sparse_series_ids": [
                "GDL2",
                "PCH2",
            ],
            "horizons": [1, 7],
            "random_state": 42,
            "sparse_exclusion_rel_wape_threshold": 0.02,
            "line_wape_guardrail_threshold": 0.01,
            "splits": {
                "test_window_days": 30,
                "validation_window_days": 28,
                "validation_folds": 3,
                "min_history_days": 365,
            },
            "features": {
                "static_feature_columns": [
                    "series_id",
                    "linea",
                    "zone",
                    "station_group",
                    "network_order",
                    "is_interchange_candidate",
                ],
                "calendar_feature_columns": list(CALENDAR_RENAME_MAP.values()),
                "weather_feature_columns": list(WEATHER_RENAME_MAP.values()),
                "service_feature_columns": [
                    "service_planned_start_minutes",
                    "service_line_end_minutes",
                    "service_line_end_day_offset",
                    "service_duration_minutes",
                    "service_has_planned_xml",
                    "service_planned_code",
                ],
                "event_feature_columns": [
                    "event_active_count",
                    "event_starting_count",
                    "event_ending_count",
                    "event_starting_estimated_attendance_sum",
                    "event_starting_unknown_attendance_count",
                    "event_high_impact_starting_count",
                ],
                "excluded_external_event_columns": [
                    "events_total_count",
                    "events_high_impact_count",
                ],
                "excluded_master_leakage_columns": [
                    "n_validations",
                    "first_seen_date",
                ],
            },
            "model": {
                "tabular": {
                    "loss": "poisson",
                    "learning_rate": 0.05,
                    "max_iter": 60,
                    "max_depth": 4,
                    "min_samples_leaf": 5,
                    "l2_regularization": 0.0,
                    "max_bins": 255,
                    "early_stopping": False,
                }
            },
            "mlflow": {"experiment_name": "daily-modeling-test"},
        },
        "mlflow": {},
    }


def _build_modeling_bundle() -> ModelingDataBundle:
    dates = pd.date_range("2024-01-01", periods=520, freq="D")
    rows: list[dict[str, object]] = []
    for index, current_date in enumerate(dates):
        if current_date != pd.Timestamp("2024-04-10"):
            rows.append(
                _build_model_base_row(
                    current_date,
                    "ALP",
                    "LINEA 1",
                    "Alpha",
                    "alpha",
                    "ALP",
                    "A",
                    1,
                    False,
                    100 + ((index + 2) % 7) * 4,
                )
            )
        if current_date != pd.Timestamp("2024-06-15"):
            rows.append(
                _build_model_base_row(
                    current_date,
                    "BET",
                    "LINEA 1",
                    "Beta",
                    "beta",
                    "BET",
                    "B",
                    2,
                    True,
                    80 + ((index + 5) % 5) * 3,
                )
            )
        if current_date in {
            dates[0],
            dates[1],
            dates[-2],
            dates[-1],
        }:
            rows.append(
                _build_model_base_row(
                    current_date,
                    "GDL2",
                    "LINEA 2",
                    "Guadalmedina",
                    "guadalmedina",
                    "GDL",
                    "C",
                    3,
                    True,
                    40 + (index % 3),
                )
            )
        if current_date in {dates[0], dates[-1]}:
            rows.append(
                _build_model_base_row(
                    current_date,
                    "PCH2",
                    "LINEA 2",
                    "Perchel",
                    "perchel",
                    "PCH",
                    "C",
                    4,
                    True,
                    30 + (index % 4),
                )
            )

    model_base = pd.DataFrame(rows)
    external_daily_features = _build_external_daily_features(dates)
    empty = pd.DataFrame()
    return ModelingDataBundle(
        station_daily_trips=empty,
        external_daily_features=external_daily_features,
        station_reference=empty,
        line_reference=empty,
        network_changes_daily=empty,
        equipment_master=empty,
        equipment_significant_master=empty,
        auxiliary_station_config=empty,
        model_base=model_base,
    )


def _build_model_base_row(
    service_date: pd.Timestamp,
    series_id: str,
    linea: str,
    estacion: str,
    station_join_key: str,
    station_abbrev: str,
    zone: str,
    network_order: int,
    is_interchange_candidate: bool,
    trip_count: float,
) -> dict[str, object]:
    return {
        "service_date": service_date,
        "series_id": series_id,
        "linea": linea,
        "estacion": estacion,
        "station_join_key": station_join_key,
        "station_abbrev": station_abbrev,
        "zone": zone,
        "station_group": station_join_key,
        "network_order": network_order,
        "is_interchange_candidate": is_interchange_candidate,
        "trip_count": float(trip_count),
    }


def _build_external_daily_features(dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, current_date in enumerate(dates):
        rows.append(
            {
                "date": current_date,
                "year": current_date.year,
                "month": current_date.month,
                "day": current_date.day,
                "quarter": current_date.quarter,
                "week_of_year": int(current_date.isocalendar().week),
                "day_of_year": current_date.day_of_year,
                "day_of_week": current_date.dayofweek,
                "day_of_week_name": current_date.day_name(),
                "is_weekend": current_date.dayofweek >= 5,
                "is_holiday": current_date.day == 1 and current_date.month == 1,
                "holiday_name": "Nuevo Anio" if current_date.day == 1 and current_date.month == 1 else None,
                "holiday_scope": "national" if current_date.day == 1 and current_date.month == 1 else None,
                "is_holiday_mmo": False,
                "is_preholiday": current_date.day == 31 and current_date.month == 12,
                "is_postholiday": current_date.day == 2 and current_date.month == 1,
                "days_to_next_holiday": 5,
                "days_since_prev_holiday": 5,
                "is_bridge_candidate": False,
                "is_month_start": current_date.is_month_start,
                "is_month_end": current_date.is_month_end,
                "temp_min_c": 10.0 + (index % 5),
                "temp_max_c": 18.0 + (index % 7),
                "temp_mean_c": 14.0 + (index % 6),
                "precip_mm": float(index % 3),
                "rain_hours": float(index % 2),
                "wind_max_kmh": 20.0 + (index % 4),
                "wind_mean_kmh": 10.0 + (index % 3),
                "humidity_mean_pct": 60.0 + (index % 5),
                "pressure_mean_hpa": 1010.0 + (index % 4),
                "weather_code": "clear" if index % 2 == 0 else "cloudy",
                "is_rainy_day": index % 3 == 0,
                "is_heavy_rain_day": False,
                "is_hot_day": False,
                "is_cold_day": False,
                "is_bad_weather_day": index % 6 == 0,
            }
        )
    return pd.DataFrame(rows)


def _build_operational_frames() -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2024-01-01", periods=520, freq="D")
    services_rows: list[dict[str, object]] = []
    events_rows: list[dict[str, object]] = []
    incidents_rows: list[dict[str, object]] = []
    for index, current_date in enumerate(dates):
        for linea in ["LINEA 1", "LINEA 2"]:
            services_rows.append(
                {
                    "service_date": current_date,
                    "linea": linea,
                    "commercial_start_minutes": 420.0,
                    "line_end_minutes": 1500.0 if linea == "LINEA 1" else 1490.0,
                    "line_end_day_offset": 1.0,
                    "planned_service_xml_name": f"{linea.replace(' ', '_')}_PLAN_{index % 3}",
                    "service_name_raw": "regular",
                }
            )
        events_rows.append(
            {
                "service_date": current_date,
                "linea": "LINEA 1",
                "estacion": "Alpha",
                "active_event_count_deduplicated": 1.0 if index % 11 == 0 else 0.0,
                "starting_event_count_deduplicated": 1.0 if index % 11 == 0 else 0.0,
                "ending_event_count_deduplicated": 1.0 if index % 11 == 1 else 0.0,
                "starting_estimated_attendance_sum_deduplicated": 5000.0 if index % 11 == 0 else 0.0,
                "starting_unknown_attendance_count_deduplicated": 0.0,
                "high_impact_starting_event_count_deduplicated": 1.0 if index % 22 == 0 else 0.0,
            }
        )
        incidents_rows.append(
            {
                "service_date": current_date,
                "impact_scope": "line",
                "mapped_linea": "LINEA 1",
                "incident_count": 1,
            }
        )
    return {
        "services_line_daily": pd.DataFrame(services_rows),
        "events_phase2a_series_daily": pd.DataFrame(events_rows),
        "incidents_daily": pd.DataFrame(incidents_rows),
    }
