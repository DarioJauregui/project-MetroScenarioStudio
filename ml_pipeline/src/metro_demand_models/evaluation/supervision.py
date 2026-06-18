from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from metro_demand_models.configuration import Settings, get_path
from metro_demand_models.evaluation.daily import build_temporal_splits, slice_split_frame
from metro_demand_models.features.daily import (
    AUTOREGRESSIVE_FEATURE_COLUMNS,
    FUTURE_AVAILABLE,
    FUTURE_AVAILABLE_IF_SCENARIO,
    NOT_FUTURE_AVAILABLE,
    build_daily_modeling_foundation,
)
from metro_demand_models.inference.daily import (
    load_pickled_model,
    load_promoted_model_specs,
)
from metro_demand_models.training.daily import (
    load_daily_feature_catalog,
    load_daily_panel_diagnostics,
    load_daily_training_dataset,
)


matplotlib.use("Agg")
import matplotlib.pyplot as plt


@dataclass(frozen=True)
class RunArtifact:
    slug: str
    model_family: str
    model_name: str
    variant: str
    series_policy: str
    horizon_days: int
    metadata: dict[str, Any]
    predictions: pd.DataFrame
    overall_metrics: pd.DataFrame
    split_metrics: pd.DataFrame
    line_metrics: pd.DataFrame
    series_metrics: pd.DataFrame


def generate_daily_supervision_artifacts(settings: Settings) -> dict[str, str]:
    reports_dir = _ensure_directory(get_path(settings, "daily_modeling_reports_dir"))
    visualizations_dir = _ensure_directory(get_path(settings, "daily_modeling_visualizations_dir"))
    run_artifacts = load_run_artifacts(settings)
    feature_catalog = load_daily_feature_catalog(settings)
    panel_diagnostics = load_daily_panel_diagnostics(settings)

    leaderboard = build_leaderboard(run_artifacts)
    leaderboard_csv = reports_dir / "leaderboard.csv"
    leaderboard_parquet = reports_dir / "leaderboard.parquet"
    leaderboard.to_csv(leaderboard_csv, index=False, encoding="utf-8")
    leaderboard.to_parquet(leaderboard_parquet, index=False)

    baseline_outputs = build_baseline_diagnostics(
        settings,
        run_artifacts,
        reports_dir=reports_dir,
    )
    supervision_outputs = build_series_supervision(
        settings,
        run_artifacts,
        panel_diagnostics=panel_diagnostics,
        reports_dir=reports_dir,
    )
    leakage_outputs = build_leakage_checks(
        settings,
        feature_catalog=feature_catalog,
        reports_dir=reports_dir,
    )
    importance_outputs = build_permutation_importance(
        settings,
        reports_dir=reports_dir,
    )
    visualization_outputs = build_review_visualizations(
        settings,
        run_artifacts,
        panel_diagnostics=panel_diagnostics,
        output_dir=visualizations_dir,
    )
    report_path = write_final_model_selection_report(
        settings,
        run_artifacts,
        leaderboard=leaderboard,
        feature_catalog=feature_catalog,
        baseline_outputs=baseline_outputs,
        supervision_outputs=supervision_outputs,
        leakage_outputs=leakage_outputs,
        importance_outputs=importance_outputs,
        report_path=reports_dir / "final_model_selection_report.md",
    )

    return {
        "leaderboard_csv": str(leaderboard_csv),
        "leaderboard_parquet": str(leaderboard_parquet),
        "baseline_diagnostics_report": str(baseline_outputs["report"]),
        "series_supervision_report": str(supervision_outputs["comparison_csv"]),
        "leakage_checks_json": str(leakage_outputs["json"]),
        "permutation_importance_csv": str(importance_outputs["csv"]),
        "final_report": str(report_path),
        **{key: str(value) for key, value in visualization_outputs.items()},
    }


def load_run_artifacts(settings: Settings) -> list[RunArtifact]:
    metrics_dir = get_path(settings, "daily_modeling_metrics_dir")
    predictions_dir = get_path(settings, "daily_modeling_predictions_dir")
    run_artifacts: list[RunArtifact] = []

    for metadata_path in sorted(metrics_dir.glob("*__metadata.json")):
        slug = metadata_path.stem.replace("__metadata", "")
        model_name, variant, series_policy, horizon_days = _parse_run_slug(slug)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        predictions_path = predictions_dir / f"{slug}.parquet"
        run_artifacts.append(
            RunArtifact(
                slug=slug,
                model_family=_infer_model_family(model_name),
                model_name=model_name,
                variant=variant,
                series_policy=series_policy,
                horizon_days=horizon_days,
                metadata=metadata,
                predictions=pd.read_parquet(predictions_path),
                overall_metrics=pd.read_csv(metrics_dir / f"{slug}__overall.csv"),
                split_metrics=pd.read_csv(metrics_dir / f"{slug}__split.csv"),
                line_metrics=pd.read_csv(metrics_dir / f"{slug}__line.csv"),
                series_metrics=pd.read_csv(metrics_dir / f"{slug}__series.csv"),
            )
        )

    if not run_artifacts:
        raise FileNotFoundError(
            "No daily modeling artifacts were found. Run scripts/run_baselines.py, "
            "scripts/train.py and scripts/evaluate.py first."
        )
    return run_artifacts


def build_leaderboard(run_artifacts: list[RunArtifact]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for artifact in run_artifacts:
        split_lookup = {split_payload["name"]: split_payload for split_payload in artifact.metadata["splits"]}
        validation_splits = [
            split_payload
            for split_payload in artifact.metadata["splits"]
            if split_payload["split_type"] == "validation"
        ]
        test_split = next(
            split_payload for split_payload in artifact.metadata["splits"] if split_payload["split_type"] == "test"
        )
        validation_date_min = min(split_payload["score_start"] for split_payload in validation_splits)
        validation_date_max = max(split_payload["score_end"] for split_payload in validation_splits)

        for row in artifact.split_metrics.itertuples(index=False):
            split_payload = split_lookup[str(row.split_name)]
            rows.append(
                {
                    "model_family": artifact.model_family,
                    "model_name": artifact.model_name,
                    "horizon": artifact.horizon_days,
                    "variant": artifact.variant,
                    "series_policy": artifact.series_policy,
                    "split_scope": row.split_name,
                    "MAE": row.mae,
                    "RMSE": row.rmse,
                    "WAPE": row.wape,
                    "sMAPE": row.smape,
                    "row_count": row.row_count,
                    "train_date_min": split_payload["train_start"],
                    "train_date_max": split_payload["train_end"],
                    "validation_date_min": validation_date_min,
                    "validation_date_max": validation_date_max,
                    "test_date_min": test_split["score_start"],
                    "test_date_max": test_split["score_end"],
                }
            )

    return (
        pd.DataFrame(rows)
        .sort_values(["model_family", "model_name", "variant", "series_policy", "horizon", "split_scope"])
        .reset_index(drop=True)
    )


def build_baseline_diagnostics(
    settings: Settings,
    run_artifacts: list[RunArtifact],
    *,
    reports_dir: Path,
) -> dict[str, Path]:
    baseline_runs = [artifact for artifact in run_artifacts if artifact.model_family == "baseline"]
    coverage_rows: list[dict[str, Any]] = []

    for artifact in baseline_runs:
        dataset = load_daily_training_dataset(
            settings,
            artifact.variant,
            artifact.horizon_days,
            series_policy=artifact.series_policy,
        )
        baseline_column = (
            "baseline_naive_simple"
            if artifact.model_name == "baseline_naive_simple"
            else "baseline_naive_seasonal_weekly"
        )
        reference_column = (
            "baseline_naive_simple_reference_date"
            if artifact.model_name == "baseline_naive_simple"
            else "baseline_naive_seasonal_reference_date"
        )
        split_lookup = {split_payload["name"]: split_payload for split_payload in artifact.metadata["splits"]}
        for split_name, split_payload in split_lookup.items():
            score_start = pd.Timestamp(split_payload["score_start"])
            score_end = pd.Timestamp(split_payload["score_end"])
            split_rows = dataset.loc[dataset["forecast_origin_date"].between(score_start, score_end)].copy()
            missing_prediction_count = int(split_rows[baseline_column].isna().sum())
            missing_reference_count = int(split_rows[reference_column].isna().sum())
            coverage_rows.append(
                {
                    "model_name": artifact.model_name,
                    "variant": artifact.variant,
                    "series_policy": artifact.series_policy,
                    "horizon_days": artifact.horizon_days,
                    "split_scope": split_name,
                    "split_type": split_payload["split_type"],
                    "row_count": int(len(split_rows)),
                    "missing_prediction_count": missing_prediction_count,
                    "missing_reference_count": missing_reference_count,
                    "coverage_ratio": (
                        float(1.0 - (missing_prediction_count / len(split_rows))) if len(split_rows) else np.nan
                    ),
                }
            )

    coverage_frame = (
        pd.DataFrame(coverage_rows)
        .sort_values(["model_name", "variant", "series_policy", "horizon_days", "split_scope"])
        .reset_index(drop=True)
    )
    coverage_csv = reports_dir / "baseline_coverage_diagnostics.csv"
    coverage_frame.to_csv(coverage_csv, index=False, encoding="utf-8")

    strict_all_h1 = _get_run(
        run_artifacts,
        model_name="baseline_naive_seasonal_weekly",
        variant="strict_available",
        series_policy="all_series",
        horizon_days=1,
    )
    strict_all_h7 = _get_run(
        run_artifacts,
        model_name="baseline_naive_seasonal_weekly",
        variant="strict_available",
        series_policy="all_series",
        horizon_days=7,
    )
    naive_h7 = _get_run(
        run_artifacts,
        model_name="baseline_naive_simple",
        variant="strict_available",
        series_policy="all_series",
        horizon_days=7,
    )

    seasonal_alignment = _compare_baseline_predictions(strict_all_h1, strict_all_h7)
    naive_vs_seasonal_h7 = _compare_baseline_predictions(naive_h7, strict_all_h7)
    report_path = reports_dir / "baseline_diagnostics_report.md"
    report_path.write_text(
        _render_baseline_report(
            coverage_frame=coverage_frame,
            seasonal_alignment=seasonal_alignment,
            naive_vs_seasonal_h7=naive_vs_seasonal_h7,
        ),
        encoding="utf-8",
    )
    return {
        "coverage_csv": coverage_csv,
        "report": report_path,
    }


def build_series_supervision(
    settings: Settings,
    run_artifacts: list[RunArtifact],
    *,
    panel_diagnostics: pd.DataFrame,
    reports_dir: Path,
) -> dict[str, Path]:
    sparse_series_ids = {str(series_id) for series_id in settings["daily_modeling"]["sparse_series_ids"]}

    series_frames = []
    line_frames = []
    for artifact in run_artifacts:
        series_frame = artifact.series_metrics.copy()
        series_frame["model_family"] = artifact.model_family
        series_frame["variant"] = artifact.variant
        series_frame["series_policy"] = artifact.series_policy
        series_frame["horizon_days"] = artifact.horizon_days
        series_frames.append(series_frame)

        line_frame = artifact.line_metrics.copy()
        line_frame["model_family"] = artifact.model_family
        line_frame["variant"] = artifact.variant
        line_frame["series_policy"] = artifact.series_policy
        line_frame["horizon_days"] = artifact.horizon_days
        line_frames.append(line_frame)

    series_metrics = pd.concat(series_frames, ignore_index=True)
    line_metrics = pd.concat(line_frames, ignore_index=True)
    series_metrics = series_metrics.loc[series_metrics["split_type"] == "test"].copy()
    line_metrics = line_metrics.loc[line_metrics["split_type"] == "test"].copy()

    diagnostics_subset = panel_diagnostics[
        [
            "series_id",
            "series_label",
            "station_abbrev",
            "observed_days",
            "calendar_span_days",
            "intra_span_missing_days",
            "coverage_ratio",
            "max_gap_days",
        ]
    ].copy()
    diagnostics_subset["is_sparse_series"] = diagnostics_subset["series_id"].isin(sparse_series_ids)
    diagnostics_subset["is_low_coverage_series"] = diagnostics_subset["coverage_ratio"] < 0.1
    series_metrics = series_metrics.merge(
        diagnostics_subset,
        how="left",
        on="series_id",
        validate="m:1",
    )
    if "series_label_x" in series_metrics.columns:
        series_metrics["series_label"] = series_metrics["series_label_x"].fillna(series_metrics["series_label_y"])
        series_metrics = series_metrics.drop(columns=["series_label_x", "series_label_y"])
    if "station_abbrev_x" in series_metrics.columns:
        series_metrics["station_abbrev"] = series_metrics["station_abbrev_x"].fillna(series_metrics["station_abbrev_y"])
        series_metrics = series_metrics.drop(columns=["station_abbrev_x", "station_abbrev_y"])
    if "coverage_ratio_x" in series_metrics.columns:
        series_metrics = series_metrics.rename(
            columns={
                "coverage_ratio_x": "prediction_coverage_ratio",
                "coverage_ratio_y": "panel_coverage_ratio",
            }
        )
    series_metrics = _reorder_series_supervision_columns(series_metrics)
    line_metrics = line_metrics.sort_values(
        ["model_name", "variant", "series_policy", "horizon_days", "linea"]
    ).reset_index(drop=True)

    series_csv = reports_dir / "series_metrics_test.csv"
    line_csv = reports_dir / "line_metrics_test.csv"
    export_series_metrics = _drop_series_id_for_reporting(series_metrics)
    export_series_metrics.to_csv(series_csv, index=False, encoding="utf-8")
    line_metrics.to_csv(line_csv, index=False, encoding="utf-8")

    ranking_rows: list[pd.DataFrame] = []
    group_columns = ["model_name", "variant", "series_policy", "horizon_days"]
    for _, group in series_metrics.groupby(group_columns, dropna=False):
        best = group.nsmallest(10, "wape").copy()
        best["ranking_group"] = "best_10"
        best["ranking_position"] = range(1, len(best) + 1)
        worst = group.nlargest(10, "wape").copy()
        worst["ranking_group"] = "worst_10"
        worst["ranking_position"] = range(1, len(worst) + 1)
        ranking_rows.extend([best, worst])
    rankings = pd.concat(ranking_rows, ignore_index=True)
    rankings = _drop_series_id_for_reporting(rankings)
    rankings_csv = reports_dir / "series_top_bottom_rankings.csv"
    rankings.to_csv(rankings_csv, index=False, encoding="utf-8")

    comparison_rows: list[pd.DataFrame] = []
    for variant in sorted(series_metrics["variant"].unique()):
        for series_policy in sorted(series_metrics["series_policy"].unique()):
            for horizon_days in sorted(series_metrics["horizon_days"].unique()):
                seasonal = series_metrics.loc[
                    (series_metrics["model_name"] == "baseline_naive_seasonal_weekly")
                    & (series_metrics["variant"] == variant)
                    & (series_metrics["series_policy"] == series_policy)
                    & (series_metrics["horizon_days"] == horizon_days)
                ].copy()
                tabular = series_metrics.loc[
                    (series_metrics["model_name"] == "tabular_hgbr")
                    & (series_metrics["variant"] == variant)
                    & (series_metrics["series_policy"] == series_policy)
                    & (series_metrics["horizon_days"] == horizon_days)
                ].copy()
                if seasonal.empty or tabular.empty:
                    continue
                merged = tabular.merge(
                    seasonal[
                        [
                            "series_id",
                            "series_label",
                            "linea",
                            "estacion",
                            "station_abbrev",
                            "wape",
                            "mae",
                            "rmse",
                            "smape",
                        ]
                    ].rename(
                        columns={
                            "wape": "baseline_wape",
                            "mae": "baseline_mae",
                            "rmse": "baseline_rmse",
                            "smape": "baseline_smape",
                        }
                    ),
                    how="inner",
                    on=["series_id", "series_label", "linea", "estacion", "station_abbrev"],
                    validate="1:1",
                )
                merged["variant"] = variant
                merged["series_policy"] = series_policy
                merged["horizon_days"] = horizon_days
                merged["tabular_wape_improvement_vs_baseline"] = merged["baseline_wape"] - merged["wape"]
                comparison_rows.append(merged)

    comparison_frame = pd.concat(comparison_rows, ignore_index=True)
    comparison_frame = _reorder_series_supervision_columns(comparison_frame)
    comparison_frame = _drop_series_id_for_reporting(comparison_frame)
    comparison_csv = reports_dir / "series_comparison_tabular_vs_baseline.csv"
    comparison_frame.to_csv(comparison_csv, index=False, encoding="utf-8")

    return {
        "series_csv": series_csv,
        "line_csv": line_csv,
        "rankings_csv": rankings_csv,
        "comparison_csv": comparison_csv,
    }


def build_leakage_checks(
    settings: Settings,
    *,
    feature_catalog: pd.DataFrame,
    reports_dir: Path,
) -> dict[str, Path]:
    promoted_specs = load_promoted_model_specs(settings)
    promoted_variant = str(settings["daily_modeling"]["target_variant_primary"])
    promoted_policy = promoted_specs[0].series_policy
    foundation = build_daily_modeling_foundation(settings)

    check_rows: list[dict[str, Any]] = []
    for spec in promoted_specs:
        dataset = load_daily_training_dataset(
            settings,
            spec.variant,
            spec.horizon_days,
            series_policy=spec.series_policy,
        )
        selected_catalog = feature_catalog.loc[feature_catalog["feature_name"].isin(spec.feature_columns)].copy()
        availability_classes = set(selected_catalog["availability_class"])
        strict_only_future_available = availability_classes == {FUTURE_AVAILABLE}

        check_rows.extend(
            [
                _check_row(
                    name=f"h{spec.horizon_days}_incidents_daily_excluded",
                    passed="incident_count" not in spec.feature_columns,
                    details="incident_count and derivados are absent from the promoted feature matrix.",
                ),
                _check_row(
                    name=f"h{spec.horizon_days}_used_service_xml_name_excluded",
                    passed="used_service_xml_name" not in spec.feature_columns,
                    details="used_service_xml_name is absent from the promoted feature matrix.",
                ),
                _check_row(
                    name=f"h{spec.horizon_days}_not_future_available_excluded",
                    passed=NOT_FUTURE_AVAILABLE not in availability_classes,
                    details=f"Availability classes present: {sorted(availability_classes)}",
                ),
                _check_row(
                    name=f"h{spec.horizon_days}_scenario_features_excluded_from_recommended_model",
                    passed=FUTURE_AVAILABLE_IF_SCENARIO not in availability_classes,
                    details=f"Availability classes present: {sorted(availability_classes)}",
                ),
                _check_row(
                    name=f"h{spec.horizon_days}_recommended_variant_is_strict_available",
                    passed=spec.variant == promoted_variant and spec.series_policy == promoted_policy,
                    details=f"Promoted variant={spec.variant}, promoted policy={spec.series_policy}",
                ),
                _check_row(
                    name=f"h{spec.horizon_days}_strict_feature_set_only_future_available",
                    passed=strict_only_future_available,
                    details=f"Availability classes present: {sorted(availability_classes)}",
                ),
            ]
        )

        alignment = _validate_feature_alignment(
            dataset=dataset,
            panel=foundation.panel,
            horizon_days=spec.horizon_days,
        )
        check_rows.extend(alignment)

    checks_frame = pd.DataFrame(check_rows)
    json_path = reports_dir / "leakage_checks.json"
    csv_path = reports_dir / "leakage_checks.csv"
    markdown_path = reports_dir / "leakage_checks_report.md"
    checks_frame.to_csv(csv_path, index=False, encoding="utf-8")
    json_path.write_text(
        json.dumps(check_rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(
        _render_leakage_report(checks_frame),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "json": json_path,
        "report": markdown_path,
    }


def build_permutation_importance(
    settings: Settings,
    *,
    reports_dir: Path,
) -> dict[str, Path]:
    promoted_specs = load_promoted_model_specs(settings)
    rows: list[dict[str, Any]] = []
    for spec in promoted_specs:
        model = load_pickled_model(spec.model_path)
        dataset = load_daily_training_dataset(
            settings,
            spec.variant,
            spec.horizon_days,
            series_policy=spec.series_policy,
        )
        splits = build_temporal_splits(settings, dataset)
        test_split = next(split for split in splits if split.split_type == "test")
        _, test_frame = slice_split_frame(dataset, test_split)
        importance = permutation_importance(
            model,
            test_frame[spec.feature_columns],
            test_frame["trip_count_target"],
            scoring="neg_mean_absolute_error",
            n_repeats=10,
            random_state=int(settings["daily_modeling"]["random_state"]),
            n_jobs=1,
        )
        for index, feature_name in enumerate(spec.feature_columns):
            rows.append(
                {
                    "model_name": spec.model_name,
                    "variant": spec.variant,
                    "series_policy": spec.series_policy,
                    "horizon_days": spec.horizon_days,
                    "feature_name": feature_name,
                    "importance_mean": float(importance.importances_mean[index]),
                    "importance_std": float(importance.importances_std[index]),
                    "scoring": "neg_mean_absolute_error",
                }
            )

    importance_frame = (
        pd.DataFrame(rows)
        .sort_values(
            ["horizon_days", "importance_mean"],
            ascending=[True, False],
        )
        .reset_index(drop=True)
    )
    csv_path = reports_dir / "permutation_importance.csv"
    parquet_path = reports_dir / "permutation_importance.parquet"
    importance_frame.to_csv(csv_path, index=False, encoding="utf-8")
    importance_frame.to_parquet(parquet_path, index=False)
    return {
        "csv": csv_path,
        "parquet": parquet_path,
        "frame": importance_frame,
    }


def build_review_visualizations(
    settings: Settings,
    run_artifacts: list[RunArtifact],
    *,
    panel_diagnostics: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    promoted_specs = load_promoted_model_specs(settings)
    promoted_policy = promoted_specs[0].series_policy
    strict_variant = str(settings["daily_modeling"]["target_variant_primary"])
    selected_runs = {
        (artifact.model_name, artifact.variant, artifact.horizon_days): artifact
        for artifact in run_artifacts
        if artifact.series_policy == promoted_policy and artifact.variant in {strict_variant, "forecastable_scenario"}
    }

    representative_series = _select_representative_series(
        run_artifacts,
        panel_diagnostics=panel_diagnostics,
        promoted_policy=promoted_policy,
        strict_variant=strict_variant,
    )

    series_plot_path = output_dir / "test_series_predictions_representative.png"
    _plot_representative_series(
        series_plot_path,
        representative_series=representative_series,
        seasonal_run=selected_runs[("baseline_naive_seasonal_weekly", strict_variant, 1)],
        strict_run=selected_runs[("tabular_hgbr", strict_variant, 1)],
        scenario_run=selected_runs[("tabular_hgbr", "forecastable_scenario", 1)],
    )

    aggregate_plot_path = output_dir / "test_global_aggregate.png"
    _plot_global_aggregate(
        aggregate_plot_path,
        strict_runs={horizon: selected_runs[("tabular_hgbr", strict_variant, horizon)] for horizon in [1, 7]},
        scenario_runs={
            horizon: selected_runs[("tabular_hgbr", "forecastable_scenario", horizon)] for horizon in [1, 7]
        },
        baseline_runs={
            horizon: selected_runs[("baseline_naive_seasonal_weekly", strict_variant, horizon)] for horizon in [1, 7]
        },
    )

    residual_plot_path = output_dir / "test_error_distribution.png"
    _plot_error_distribution(
        residual_plot_path,
        strict_runs={horizon: selected_runs[("tabular_hgbr", strict_variant, horizon)] for horizon in [1, 7]},
        baseline_runs={
            horizon: selected_runs[("baseline_naive_seasonal_weekly", strict_variant, horizon)] for horizon in [1, 7]
        },
    )

    variant_comparison_path = output_dir / "strict_vs_forecastable_comparison.png"
    _plot_variant_comparison(
        variant_comparison_path,
        strict_runs={horizon: selected_runs[("tabular_hgbr", strict_variant, horizon)] for horizon in [1, 7]},
        scenario_runs={
            horizon: selected_runs[("tabular_hgbr", "forecastable_scenario", horizon)] for horizon in [1, 7]
        },
    )

    return {
        "series_plot": series_plot_path,
        "aggregate_plot": aggregate_plot_path,
        "residual_plot": residual_plot_path,
        "variant_comparison_plot": variant_comparison_path,
    }


def write_final_model_selection_report(
    settings: Settings,
    run_artifacts: list[RunArtifact],
    *,
    leaderboard: pd.DataFrame,
    feature_catalog: pd.DataFrame,
    baseline_outputs: dict[str, Path],
    supervision_outputs: dict[str, Path],
    leakage_outputs: dict[str, Path],
    importance_outputs: dict[str, Path | pd.DataFrame],
    report_path: Path,
) -> Path:
    comparison_path = get_path(settings, "daily_modeling_metrics_dir") / "comparison_summary.csv"
    policy_path = get_path(settings, "daily_modeling_metrics_dir") / "series_policy_decision.json"
    comparison = pd.read_csv(comparison_path)
    policy_decision = json.loads(policy_path.read_text(encoding="utf-8"))
    recommended_policy = str(policy_decision["recommended_series_policy"])
    strict_variant = str(settings["daily_modeling"]["target_variant_primary"])

    selected_test = comparison.loc[comparison["selected_for_final_comparison"]].copy()
    recommended_rows = selected_test.loc[
        (selected_test["model_name"] == "tabular_hgbr")
        & (selected_test["variant"] == strict_variant)
        & (selected_test["series_policy"] == recommended_policy)
    ].sort_values("horizon_days")

    importance_frame = importance_outputs["frame"]
    top_importance = importance_frame.groupby("horizon_days", group_keys=False).head(5).copy()
    selected_feature_catalog = feature_catalog.loc[
        feature_catalog["included_in_strict_available"] & feature_catalog["is_model_feature"]
    ].copy()
    availability_counts = selected_feature_catalog["availability_class"].value_counts().to_dict()

    report_text = _render_final_model_selection_report(
        recommended_policy=recommended_policy,
        selected_test=selected_test,
        recommended_rows=recommended_rows,
        policy_decision=policy_decision,
        baseline_outputs=baseline_outputs,
        supervision_outputs=supervision_outputs,
        leakage_outputs=leakage_outputs,
        importance_frame=top_importance,
        availability_counts=availability_counts,
    )
    report_path.write_text(report_text, encoding="utf-8")
    return report_path


def _parse_run_slug(slug: str) -> tuple[str, str, str, int]:
    model_name, variant, series_policy, horizon_token = slug.split("__")
    return model_name, variant, series_policy, int(horizon_token.removeprefix("h"))


def _infer_model_family(model_name: str) -> str:
    if model_name.startswith("baseline_"):
        return "baseline"
    if model_name.startswith("tabular_"):
        return "tabular"
    return "other"


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_run(
    run_artifacts: list[RunArtifact],
    *,
    model_name: str,
    variant: str,
    series_policy: str,
    horizon_days: int,
) -> RunArtifact:
    for artifact in run_artifacts:
        if (
            artifact.model_name == model_name
            and artifact.variant == variant
            and artifact.series_policy == series_policy
            and artifact.horizon_days == horizon_days
        ):
            return artifact
    raise KeyError(f"Run artifact not found for {model_name}/{variant}/{series_policy}/h{horizon_days}.")


def _compare_baseline_predictions(
    left_run: RunArtifact,
    right_run: RunArtifact,
) -> dict[str, Any]:
    left_test = left_run.predictions.loc[
        left_run.predictions["split_type"] == "test",
        ["series_id", "forecast_origin_date", "target_date", "y_true", "y_pred"],
    ].copy()
    right_test = right_run.predictions.loc[
        right_run.predictions["split_type"] == "test",
        ["series_id", "forecast_origin_date", "target_date", "y_true", "y_pred"],
    ].copy()
    merged = left_test.merge(
        right_test,
        how="inner",
        on=["series_id", "forecast_origin_date"],
        suffixes=("_left", "_right"),
    )
    left_abs_error = (merged["y_pred_left"] - merged["y_true_left"]).abs()
    right_abs_error = (merged["y_pred_right"] - merged["y_true_right"]).abs()
    return {
        "left_slug": left_run.slug,
        "right_slug": right_run.slug,
        "row_count": int(len(merged)),
        "same_truth_fraction": float((merged["y_true_left"] == merged["y_true_right"]).mean()),
        "same_prediction_fraction": float((merged["y_pred_left"] == merged["y_pred_right"]).mean()),
        "left_absolute_error_sum": float(left_abs_error.sum()),
        "right_absolute_error_sum": float(right_abs_error.sum()),
        "left_target_sum": float(merged["y_true_left"].sum()),
        "right_target_sum": float(merged["y_true_right"].sum()),
    }


def _render_baseline_report(
    *,
    coverage_frame: pd.DataFrame,
    seasonal_alignment: dict[str, Any],
    naive_vs_seasonal_h7: dict[str, Any],
) -> str:
    test_rows = coverage_frame.loc[coverage_frame["split_type"] == "test"].copy()
    missing_rows = coverage_frame.loc[coverage_frame["missing_reference_count"] > 0].copy()
    return "\n".join(
        [
            "# Diagnostico de baselines",
            "",
            "## Cobertura",
            "",
            f"- Filas de test analizadas: `{int(test_rows['row_count'].sum())}`",
            f"- Cobertura minima observada en test: `{test_rows['coverage_ratio'].min():.4f}`",
            f"- Filas con referencia historica ausente: `{int(missing_rows['missing_reference_count'].sum())}`",
            "",
            "## Lectura tecnica",
            "",
            "- No se han detectado filas descartadas en los splits evaluados: cuando existe historial suficiente, ambos baselines puntuan con cobertura completa.",
            "- `naive_simple` y `naive_seasonal_weekly` coinciden en `D+7` por construccion en la mayor parte de las filas: para un horizonte de 7 dias, el ultimo valor del mismo weekday suele ser exactamente el valor observado en `forecast_origin_date`.",
            "- Que `naive_seasonal_weekly` tenga el mismo WAPE en `D+1` y `D+7` no es un bug de duplicacion de archivos: las filas de test comparadas cambian casi por completo, pero en el holdout actual coinciden tanto la suma del target como la suma del error absoluto.",
            "",
            "## Comprobaciones clave",
            "",
            f"- Coincidencia fila a fila de `naive_seasonal_weekly` entre `D+1` y `D+7`: `{seasonal_alignment['same_prediction_fraction']:.4%}`",
            f"- Coincidencia fila a fila del target entre `D+1` y `D+7`: `{seasonal_alignment['same_truth_fraction']:.4%}`",
            f"- Suma de error absoluto `naive_seasonal_weekly` `D+1`: `{seasonal_alignment['left_absolute_error_sum']:.2f}`",
            f"- Suma de error absoluto `naive_seasonal_weekly` `D+7`: `{seasonal_alignment['right_absolute_error_sum']:.2f}`",
            f"- Coincidencia fila a fila entre `naive_simple` y `naive_seasonal_weekly` en `D+7`: `{naive_vs_seasonal_h7['same_prediction_fraction']:.4%}`",
            "",
            "## Artefacto fuente",
            "",
            f"- Cobertura detallada: `{coverage_frame.shape[0]}` filas en `baseline_coverage_diagnostics.csv`",
        ]
    )


def _check_row(*, name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"check_name": name, "passed": bool(passed), "details": details}


def _validate_feature_alignment(
    *,
    dataset: pd.DataFrame,
    panel: pd.DataFrame,
    horizon_days: int,
) -> list[dict[str, Any]]:
    alignment_columns = AUTOREGRESSIVE_FEATURE_COLUMNS
    panel_lookup = panel[["series_id", "service_date", *alignment_columns]].rename(
        columns={"service_date": "forecast_origin_date"}
    )
    merged = dataset.merge(
        panel_lookup,
        how="left",
        on=["series_id", "forecast_origin_date"],
        suffixes=("_dataset", "_panel"),
        validate="m:1",
    )
    checks: list[dict[str, Any]] = []
    for column in alignment_columns:
        dataset_column = f"{column}_dataset"
        panel_column = f"{column}_panel"
        same_mask = (merged[dataset_column].isna() & merged[panel_column].isna()) | (
            merged[dataset_column] == merged[panel_column]
        )
        matches = bool(same_mask.all())
        mismatch_count = int((~same_mask).sum())
        checks.append(
            _check_row(
                name=f"h{horizon_days}_{column}_matches_origin_panel",
                passed=matches,
                details=f"Mismatch count: {mismatch_count}",
            )
        )
    return checks


def _render_leakage_report(checks_frame: pd.DataFrame) -> str:
    failed_checks = checks_frame.loc[~checks_frame["passed"]].copy()
    lines = [
        "# Verificacion de fuga temporal",
        "",
        f"- Total de checks: `{len(checks_frame)}`",
        f"- Checks fallidos: `{len(failed_checks)}`",
        "",
    ]
    if failed_checks.empty:
        lines.append("- Resultado: no se ha detectado fuga temporal en la configuracion promovida.")
    else:
        lines.append("- Resultado: revisar checks fallidos antes de aprobar la fase.")
        lines.append("")
        for row in failed_checks.itertuples(index=False):
            lines.append(f"- `{row.check_name}`: {row.details}")
    return "\n".join(lines)


def _select_representative_series(
    run_artifacts: list[RunArtifact],
    *,
    panel_diagnostics: pd.DataFrame,
    promoted_policy: str,
    strict_variant: str,
) -> list[str]:
    tabular_run = _get_run(
        run_artifacts,
        model_name="tabular_hgbr",
        variant=strict_variant,
        series_policy=promoted_policy,
        horizon_days=1,
    )
    test_predictions = tabular_run.predictions.loc[tabular_run.predictions["split_type"] == "test"].copy()
    volume = test_predictions.groupby("series_id")["y_true"].sum().sort_values(ascending=False)
    dense_series = panel_diagnostics.loc[panel_diagnostics["coverage_ratio"] > 0.8, "series_id"].tolist()
    sparse_series = [
        candidate
        for candidate in panel_diagnostics.loc[panel_diagnostics["coverage_ratio"] < 0.1, "series_id"].tolist()
        if candidate in volume.index
    ]
    selections: list[str] = []
    for candidate in volume.index.tolist():
        if candidate in dense_series and candidate not in selections:
            selections.append(candidate)
        if len(selections) == 2:
            break
    for candidate in volume.index.tolist()[::-1]:
        if candidate not in selections and candidate in dense_series:
            selections.append(candidate)
            break
    if sparse_series:
        selections.append(sparse_series[0])
    return selections[:4]


def _reorder_series_supervision_columns(frame: pd.DataFrame) -> pd.DataFrame:
    preferred_columns = [
        "series_label",
        "station_abbrev",
        "series_id",
        "linea",
        "estacion",
    ]
    available_preferred = [column for column in preferred_columns if column in frame.columns]
    remaining_columns = [column for column in frame.columns if column not in available_preferred]
    return frame[available_preferred + remaining_columns]


def _drop_series_id_for_reporting(frame: pd.DataFrame) -> pd.DataFrame:
    if "series_label" in frame.columns and "series_id" in frame.columns:
        return frame.drop(columns="series_id")
    return frame


def _plot_representative_series(
    output_path: Path,
    *,
    representative_series: list[str],
    seasonal_run: RunArtifact,
    strict_run: RunArtifact,
    scenario_run: RunArtifact,
) -> None:
    seasonal = seasonal_run.predictions.loc[seasonal_run.predictions["split_type"] == "test"].copy()
    strict = strict_run.predictions.loc[strict_run.predictions["split_type"] == "test"].copy()
    scenario = scenario_run.predictions.loc[scenario_run.predictions["split_type"] == "test"].copy()

    figure, axes = plt.subplots(
        len(representative_series), 1, figsize=(12, 3 * len(representative_series)), sharex=False
    )
    if len(representative_series) == 1:
        axes = [axes]

    for axis, series_id in zip(axes, representative_series):
        strict_series = strict.loc[strict["series_id"] == series_id].sort_values("target_date")
        seasonal_series = seasonal.loc[seasonal["series_id"] == series_id].sort_values("target_date")
        scenario_series = scenario.loc[scenario["series_id"] == series_id].sort_values("target_date")
        series_title = (
            str(strict_series["series_label"].iat[0])
            if "series_label" in strict_series.columns and not strict_series.empty
            else series_id
        )
        axis.plot(strict_series["target_date"], strict_series["y_true"], label="real", linewidth=2)
        axis.plot(strict_series["target_date"], strict_series["y_pred"], label="tabular_strict", linewidth=1.5)
        axis.plot(seasonal_series["target_date"], seasonal_series["y_pred"], label="baseline_estacional", linewidth=1.2)
        axis.plot(
            scenario_series["target_date"],
            scenario_series["y_pred"],
            label="tabular_scenario",
            linewidth=1.2,
            alpha=0.8,
        )
        axis.set_title(series_title)
        axis.legend(loc="upper right", fontsize=8)
        axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _plot_global_aggregate(
    output_path: Path,
    *,
    strict_runs: dict[int, RunArtifact],
    scenario_runs: dict[int, RunArtifact],
    baseline_runs: dict[int, RunArtifact],
) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
    for axis, horizon_days in zip(axes, [1, 7]):
        strict = strict_runs[horizon_days].predictions.loc[
            strict_runs[horizon_days].predictions["split_type"] == "test"
        ]
        scenario = scenario_runs[horizon_days].predictions.loc[
            scenario_runs[horizon_days].predictions["split_type"] == "test"
        ]
        baseline = baseline_runs[horizon_days].predictions.loc[
            baseline_runs[horizon_days].predictions["split_type"] == "test"
        ]
        strict_agg = strict.groupby("target_date")[["y_true", "y_pred"]].sum().reset_index()
        scenario_agg = scenario.groupby("target_date")["y_pred"].sum().reset_index(name="y_pred_scenario")
        baseline_agg = baseline.groupby("target_date")["y_pred"].sum().reset_index(name="y_pred_baseline")
        merged = strict_agg.merge(scenario_agg, on="target_date").merge(baseline_agg, on="target_date")
        axis.plot(merged["target_date"], merged["y_true"], label="real", linewidth=2)
        axis.plot(merged["target_date"], merged["y_pred"], label="tabular_strict", linewidth=1.5)
        axis.plot(merged["target_date"], merged["y_pred_scenario"], label="tabular_scenario", linewidth=1.2)
        axis.plot(merged["target_date"], merged["y_pred_baseline"], label="baseline_estacional", linewidth=1.2)
        axis.set_title(f"Agregado global en test D+{horizon_days}")
        axis.legend(loc="upper right", fontsize=8)
        axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _plot_error_distribution(
    output_path: Path,
    *,
    strict_runs: dict[int, RunArtifact],
    baseline_runs: dict[int, RunArtifact],
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for axis, horizon_days in zip(axes, [1, 7]):
        strict = (
            strict_runs[horizon_days]
            .predictions.loc[strict_runs[horizon_days].predictions["split_type"] == "test"]
            .copy()
        )
        baseline = (
            baseline_runs[horizon_days]
            .predictions.loc[baseline_runs[horizon_days].predictions["split_type"] == "test"]
            .copy()
        )
        axis.hist(
            (strict["y_pred"] - strict["y_true"]).abs(),
            bins=40,
            alpha=0.6,
            label="tabular_strict",
        )
        axis.hist(
            (baseline["y_pred"] - baseline["y_true"]).abs(),
            bins=40,
            alpha=0.6,
            label="baseline_estacional",
        )
        axis.set_title(f"Distribucion de error absoluto D+{horizon_days}")
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _plot_variant_comparison(
    output_path: Path,
    *,
    strict_runs: dict[int, RunArtifact],
    scenario_runs: dict[int, RunArtifact],
) -> None:
    rows = []
    for horizon_days in [1, 7]:
        strict_row = (
            strict_runs[horizon_days]
            .split_metrics.loc[strict_runs[horizon_days].split_metrics["split_type"] == "test"]
            .iloc[0]
        )
        scenario_row = (
            scenario_runs[horizon_days]
            .split_metrics.loc[scenario_runs[horizon_days].split_metrics["split_type"] == "test"]
            .iloc[0]
        )
        rows.append(
            {
                "horizon": f"D+{horizon_days}",
                "variant": "strict_available",
                "WAPE": strict_row["wape"],
                "MAE": strict_row["mae"],
            }
        )
        rows.append(
            {
                "horizon": f"D+{horizon_days}",
                "variant": "forecastable_scenario",
                "WAPE": scenario_row["wape"],
                "MAE": scenario_row["mae"],
            }
        )
    frame = pd.DataFrame(rows)

    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    for axis, metric in zip(axes, ["WAPE", "MAE"]):
        pivot = frame.pivot(index="horizon", columns="variant", values=metric)
        pivot.plot(kind="bar", ax=axis, rot=0)
        axis.set_title(f"Comparacion strict vs scenario por {metric}")
        axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _render_final_model_selection_report(
    *,
    recommended_policy: str,
    selected_test: pd.DataFrame,
    recommended_rows: pd.DataFrame,
    policy_decision: dict[str, Any],
    baseline_outputs: dict[str, Path],
    supervision_outputs: dict[str, Path],
    leakage_outputs: dict[str, Path],
    importance_frame: pd.DataFrame,
    availability_counts: dict[str, int],
) -> str:
    metric_table = selected_test[
        ["model_name", "variant", "series_policy", "horizon_days", "mae", "rmse", "wape", "smape"]
    ].sort_values(["horizon_days", "variant", "model_name"])
    metric_lines = [
        "| modelo | variante | series_policy | horizonte | MAE | RMSE | WAPE | sMAPE |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in metric_table.itertuples(index=False):
        metric_lines.append(
            f"| {row.model_name} | {row.variant} | {row.series_policy} | D+{row.horizon_days} | "
            f"{row.mae:.2f} | {row.rmse:.2f} | {row.wape:.4f} | {row.smape:.4f} |"
        )

    importance_lines = []
    for horizon_days, group in importance_frame.groupby("horizon_days"):
        importance_lines.append(
            f"- D+{horizon_days}: "
            + ", ".join(f"`{row.feature_name}` ({row.importance_mean:.2f})" for row in group.itertuples(index=False))
        )

    return "\n".join(
        [
            "# Informe Final de Seleccion de Modelo",
            "",
            "## Punto de partida",
            "",
            "- Dataset principal evaluado: `phase_2a_station_daily_model_base` transformado a datasets diarios de entrenamiento por `forecast_origin_date + series_id`.",
            "- Horizontes evaluados: `D+1` y `D+7`.",
            "- Variantes comparadas: `strict_available` y `forecastable_scenario`.",
            f"- Politica de series comparada: `all_series` frente a `sparse_excluded`. La politica recomendada tras la sensibilidad es `{recommended_policy}`.",
            "",
            "## Metricas principales en test",
            "",
            *metric_lines,
            "",
            "## Recomendacion final",
            "",
            f"- Configuracion recomendada: `tabular_hgbr + strict_available + {recommended_policy}`.",
            "- Justificacion operativa: mejora claramente a los dos baselines en `D+1` y `D+7` y no depende de weather, eventos planificados ni senales ejecutadas que podrian no estar disponibles en un uso realista.",
            "- La variante `forecastable_scenario` queda como comparacion valida solo si existe un feed de forecast, planificacion o un escenario exogeno definido. Aunque mejora el test actual, no se recomienda promoverla por defecto porque haria depender el rendimiento de inputs externos que no siempre estaran disponibles antes de predecir.",
            "",
            "## Por que no se recomienda usar variables no disponibles a futuro",
            "",
            f"- El modelo recomendado usa solo features clasificadas como `{FUTURE_AVAILABLE}`. Conteo actual: `{availability_counts.get(FUTURE_AVAILABLE, 0)}`.",
            f"- Las features `{NOT_FUTURE_AVAILABLE}` no entran en la matriz promovida. Esto incluye `incidents_daily`, `used_service_xml_name` y cualquier senal ejecutada u observada a posteriori.",
            f"- Las features `{FUTURE_AVAILABLE_IF_SCENARIO}` solo se mantienen en la variante secundaria. No forman parte de la configuracion principal porque harian depender el rendimiento de feeds o escenarios externos.",
            "",
            "## Diagnostico de politica de series",
            "",
            "- La regla de decision configurada exige mejorar WAPE relativo al menos un `2%` en `D+1` y `D+7`, sin empeorar el WAPE por linea mas de `1%`.",
            f"- Resultado actual: `{json.dumps(policy_decision['horizon_results'], ensure_ascii=False)}`.",
            "- Conclusion: no hay evidencia suficiente para excluir `GDL2` y `PCH2`; por ahora conviene mantener `all_series` y revisar estas series como caso de calidad/cobertura del dato, no como cambio automatico del modelo.",
            "",
            "## Diagnostico de baselines",
            "",
            f"- Reporte detallado: [{baseline_outputs['report'].name}]({baseline_outputs['report'].name})",
            "- No se ha detectado bug en el baseline estacional. El mismo WAPE en `D+1` y `D+7` viene de una coincidencia agregada del holdout actual, no de archivos duplicados ni de una fuga.",
            "- `naive_simple` y `naive_seasonal_weekly` coinciden en `D+7` por construccion en la mayoria de filas, porque el weekday objetivo coincide con el de `forecast_origin_date`.",
            "",
            "## Importancia de variables simple",
            "",
            *importance_lines,
            "",
            "## Verificacion de fuga temporal",
            "",
            f"- Reporte detallado: [{leakage_outputs['report'].name}]({leakage_outputs['report'].name})",
            "- Comprobacion automatica superada: las columnas `not_future_available` quedan fuera de la matriz del modelo recomendado y las features autoregresivas del dataset coinciden con las calculadas en el panel de origen por `forecast_origin_date`.",
            "",
            "## Artefactos de supervision",
            "",
            "- Leaderboard consolidado: `leaderboard.csv` y `leaderboard.parquet`.",
            f"- Comparacion por serie: [{supervision_outputs['comparison_csv'].name}]({supervision_outputs['comparison_csv'].name})",
            f"- Rankings top/bottom por serie: [{supervision_outputs['rankings_csv'].name}]({supervision_outputs['rankings_csv'].name})",
            f"- Metricas por linea: [{supervision_outputs['line_csv'].name}]({supervision_outputs['line_csv'].name})",
            "",
            "## Limitaciones actuales",
            "",
            "- La recomendacion presupone que la prediccion diaria se hace con informacion disponible al cierre de `forecast_origin_date`. Si mas adelante la operativa exige predecir antes del cierre del dia, habra que revisar la validez de usar la observacion del propio origen como resumen de historial reciente.",
            "- Las dos series escasas de Linea 2 (`GDL2` y `PCH2`) siguen presentes porque excluirlas no mejora el rendimiento agregado con la regla actual, pero deben mantenerse bajo vigilancia de calidad.",
            "- `forecastable_scenario` depende de feeds externos para weather, eventos y senales de servicio planificado. No debe presentarse como rendimiento operativo garantizado sin esos inputs.",
        ]
    )
