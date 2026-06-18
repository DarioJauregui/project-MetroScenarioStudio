from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from metro_demand_models.configuration import Settings, get_path


EPSILON = 1e-9
DEFAULT_TOP_N = 20

PREDICTION_KEYS = [
    "forecast_origin_date",
    "target_date",
    "series_id",
    "linea",
    "estacion",
    "horizon_days",
    "split_name",
    "split_type",
]

CONTEXT_COLUMNS = [
    "forecast_origin_date",
    "target_date",
    "series_id",
    "calendar_holiday_name",
    "calendar_holiday_scope",
    "calendar_is_holiday",
    "calendar_is_preholiday",
    "calendar_is_postholiday",
    "calendar_is_bridge_candidate",
    "event_active_count",
    "event_starting_count",
    "event_ending_count",
    "event_starting_estimated_attendance_sum",
    "event_starting_unknown_attendance_count",
    "event_high_impact_starting_count",
    "weather_is_bad_weather_day",
    "weather_is_heavy_rain_day",
    "weather_is_rainy_day",
    "weather_precip_mm",
    "weather_rain_hours",
    "service_duration_minutes",
    "service_has_planned_xml",
    "service_planned_code",
]

SEGMENT_FLAG_COLUMNS = [
    "is_holiday",
    "is_preholiday",
    "is_postholiday",
    "is_semana_santa",
    "event_day",
    "high_impact_event_day",
    "bad_weather_day",
    "heavy_rain_day",
]


@dataclass(frozen=True)
class SegmentDefinition:
    name: str
    mask: pd.Series
    description: str = ""


def generate_special_day_error_analysis(
    settings: Settings,
    *,
    series_policy: str = "all_series",
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, str]:
    """Generate segmented diagnostics for special days and large deviations."""

    metrics_dir = _ensure_directory(get_path(settings, "daily_modeling_metrics_dir"))
    reports_dir = _ensure_directory(get_path(settings, "daily_modeling_reports_dir"))
    project_root = Path(settings["runtime"]["project_root"])
    docs_results_dir = _ensure_directory(project_root / "docs" / "04_results")
    memory_tables_dir = _ensure_directory(project_root / "docs" / "05_memory_support" / "assets" / "tables")

    comparison = load_special_day_comparison_frame(
        settings,
        series_policy=series_policy,
    )
    top_rows = build_top_deviation_rows(comparison, top_n=top_n)
    segment_definitions = build_segment_definitions(
        comparison,
        top_deviation_dates=_top_target_dates(
            top_rows,
            rank_type="baseline_seasonal_deviation",
            analysis_scope="network_day",
        ),
        top_tabular_worse_dates=_top_target_dates(
            top_rows,
            rank_type="tabular_strict_worse_than_seasonal",
            analysis_scope="network_day",
        ),
    )
    segment_metrics = summarize_segments(comparison, segment_definitions)
    main_results = build_tfm_main_results_summary(
        settings,
        series_policy=series_policy,
    )
    availability_summary = build_external_variable_availability_summary(comparison)

    segment_metrics_path = metrics_dir / "segment_metrics.csv"
    top_rows_path = metrics_dir / "top_deviation_days.csv"
    segment_metrics.to_csv(segment_metrics_path, index=False, encoding="utf-8")
    top_rows.to_csv(top_rows_path, index=False, encoding="utf-8")

    segment_summary_path = memory_tables_dir / "segment_metrics_summary.md"
    top_deviation_md_path = memory_tables_dir / "top_deviation_days.md"
    main_results_md_path = memory_tables_dir / "tfm_main_results_summary.md"
    main_results_csv_path = memory_tables_dir / "tfm_main_results_summary.csv"
    segment_metrics_summary_csv = memory_tables_dir / "segment_metrics_summary.csv"
    top_deviation_csv = memory_tables_dir / "top_deviation_days.csv"

    segment_metrics.to_csv(
        segment_metrics_summary_csv,
        index=False,
        encoding="utf-8",
    )
    top_rows.to_csv(top_deviation_csv, index=False, encoding="utf-8")
    main_results.to_csv(main_results_csv_path, index=False, encoding="utf-8")

    segment_summary_path.write_text(
        dataframe_to_markdown(_format_segment_metrics_for_memory(segment_metrics)),
        encoding="utf-8",
    )
    top_deviation_md_path.write_text(
        dataframe_to_markdown(_format_top_rows_for_memory(top_rows)),
        encoding="utf-8",
    )
    main_results_md_path.write_text(
        render_main_results_markdown(main_results),
        encoding="utf-8",
    )
    _update_memory_asset_manifest(
        project_root,
        memory_tables_dir=memory_tables_dir,
        table_paths={
            "segment_metrics_summary_csv": segment_metrics_summary_csv,
            "segment_metrics_summary_md": segment_summary_path,
            "top_deviation_days_csv": top_deviation_csv,
            "top_deviation_days_md": top_deviation_md_path,
            "tfm_main_results_summary_csv": main_results_csv_path,
            "tfm_main_results_summary_md": main_results_md_path,
        },
    )

    report_text = render_special_day_report(
        comparison=comparison,
        segment_metrics=segment_metrics,
        top_rows=top_rows,
        main_results=main_results,
        availability_summary=availability_summary,
        artifact_paths={
            "segment_metrics_csv": segment_metrics_path.relative_to(project_root),
            "top_deviation_days_csv": top_rows_path.relative_to(project_root),
            "segment_metrics_summary_md": segment_summary_path.relative_to(project_root),
            "top_deviation_days_md": top_deviation_md_path.relative_to(project_root),
            "tfm_main_results_summary_md": main_results_md_path.relative_to(project_root),
        },
    )
    report_path = reports_dir / "special_day_error_analysis.md"
    docs_report_path = docs_results_dir / "special_day_error_analysis.md"
    report_path.write_text(report_text, encoding="utf-8")
    docs_report_path.write_text(report_text, encoding="utf-8")

    return {
        "segment_metrics_csv": str(segment_metrics_path),
        "top_deviation_days_csv": str(top_rows_path),
        "special_day_report": str(report_path),
        "docs_special_day_report": str(docs_report_path),
        "segment_metrics_summary_md": str(segment_summary_path),
        "top_deviation_days_md": str(top_deviation_md_path),
        "tfm_main_results_summary_md": str(main_results_md_path),
        "tfm_main_results_summary_csv": str(main_results_csv_path),
    }


def load_special_day_comparison_frame(
    settings: Settings,
    *,
    series_policy: str = "all_series",
) -> pd.DataFrame:
    frames = [
        _load_horizon_comparison(settings, horizon_days, series_policy=series_policy)
        for horizon_days in settings["daily_modeling"]["horizons"]
    ]
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["horizon_days", "target_date", "series_id"])
        .reset_index(drop=True)
    )


def summarize_segments(
    comparison: pd.DataFrame,
    segment_definitions: list[SegmentDefinition],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon_days, horizon_frame in comparison.groupby("horizon_days", sort=True):
        for definition in segment_definitions:
            mask = definition.mask.reindex(horizon_frame.index, fill_value=False)
            segment_frame = horizon_frame.loc[mask].copy()
            row: dict[str, Any] = {
                "horizon_days": int(horizon_days),
                "segment_name": definition.name,
                "segment_description": definition.description,
            }
            row.update(_prefixed_metrics(segment_frame, "baseline_seasonal", "y_pred_seasonal"))
            row.update(_prefixed_metrics(segment_frame, "tabular_strict", "y_pred_tabular_strict"))
            row.update(
                _prefixed_metrics(
                    segment_frame,
                    "tabular_forecastable",
                    "y_pred_tabular_forecastable",
                )
            )
            row["row_count"] = int(len(segment_frame))
            row["target_sum"] = float(segment_frame["y_true"].sum())
            row["tabular_strict_relative_wape_improvement_vs_seasonal"] = _relative_improvement(
                row["baseline_seasonal_wape"],
                row["tabular_strict_wape"],
            )
            row["forecastable_relative_wape_improvement_vs_strict"] = _relative_improvement(
                row["tabular_strict_wape"],
                row["tabular_forecastable_wape"],
            )
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["horizon_days", "segment_name"]).reset_index(drop=True)


def build_top_deviation_rows(comparison: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    prepared = comparison.copy()
    missing_flag_columns = [column for column in SEGMENT_FLAG_COLUMNS if column not in prepared.columns]
    if missing_flag_columns:
        prepared = _add_segment_flags(prepared)
    enriched = add_error_columns(prepared)
    for horizon_days, horizon_frame in enriched.groupby("horizon_days", sort=True):
        horizon_total = float(horizon_frame["y_true"].abs().sum())
        network = _aggregate_network_days(horizon_frame)
        network = add_error_columns(network, wape_denominator=horizon_total)
        rows.append(
            _select_ranked_rows(
                network,
                analysis_scope="network_day",
                rank_type="baseline_seasonal_deviation",
                sort_column="seasonal_abs_error",
                top_n=top_n,
            )
        )
        rows.append(
            _select_ranked_rows(
                network,
                analysis_scope="network_day",
                rank_type="tabular_strict_worse_than_seasonal",
                sort_column="tabular_strict_error_delta_vs_seasonal",
                top_n=top_n,
            )
        )
        series_rows = horizon_frame.copy()
        series_rows["seasonal_wape_contribution"] = (
            series_rows["seasonal_abs_error"] / horizon_total if horizon_total else np.nan
        )
        rows.append(
            _select_ranked_rows(
                series_rows,
                analysis_scope="series_day",
                rank_type="baseline_seasonal_deviation",
                sort_column="seasonal_abs_error",
                top_n=top_n,
            )
        )
        rows.append(
            _select_ranked_rows(
                series_rows,
                analysis_scope="series_day",
                rank_type="tabular_strict_worse_than_seasonal",
                sort_column="tabular_strict_error_delta_vs_seasonal",
                top_n=top_n,
            )
        )

    output = pd.concat(rows, ignore_index=True)
    output["tabular_strict_improves_vs_seasonal"] = (
        output["tabular_strict_improves_vs_seasonal"].map(bool).astype(object)
    )
    return output.sort_values(["horizon_days", "analysis_scope", "rank_type", "rank_position"]).reset_index(drop=True)


def add_error_columns(
    frame: pd.DataFrame,
    *,
    wape_denominator: float | None = None,
) -> pd.DataFrame:
    enriched = frame.copy()
    denominator = float(enriched["y_true"].abs().sum()) if wape_denominator is None else float(wape_denominator)
    enriched["seasonal_abs_error"] = (enriched["y_pred_seasonal"] - enriched["y_true"]).abs()
    enriched["seasonal_relative_error"] = np.where(
        enriched["y_true"].abs() > EPSILON,
        enriched["seasonal_abs_error"] / enriched["y_true"].abs(),
        np.nan,
    )
    enriched["seasonal_wape_contribution"] = enriched["seasonal_abs_error"] / denominator if denominator else np.nan
    enriched["real_baseline_ratio"] = np.where(
        enriched["y_pred_seasonal"].abs() > EPSILON,
        enriched["y_true"] / enriched["y_pred_seasonal"],
        np.nan,
    )
    enriched["real_minus_baseline"] = enriched["y_true"] - enriched["y_pred_seasonal"]
    enriched["tabular_strict_abs_error"] = (enriched["y_pred_tabular_strict"] - enriched["y_true"]).abs()
    enriched["tabular_strict_error_delta_vs_seasonal"] = (
        enriched["tabular_strict_abs_error"] - enriched["seasonal_abs_error"]
    )
    enriched["tabular_strict_improves_vs_seasonal"] = (
        (enriched["tabular_strict_abs_error"] < enriched["seasonal_abs_error"]).map(bool).astype(object)
    )
    if "y_pred_tabular_forecastable" in enriched.columns:
        enriched["tabular_forecastable_abs_error"] = (
            enriched["y_pred_tabular_forecastable"] - enriched["y_true"]
        ).abs()
        enriched["forecastable_error_delta_vs_strict"] = (
            enriched["tabular_forecastable_abs_error"] - enriched["tabular_strict_abs_error"]
        )
    return enriched


def build_segment_definitions(
    comparison: pd.DataFrame,
    *,
    top_deviation_dates: set[pd.Timestamp],
    top_tabular_worse_dates: set[pd.Timestamp],
) -> list[SegmentDefinition]:
    special_flags = comparison[SEGMENT_FLAG_COLUMNS].any(axis=1)
    return [
        SegmentDefinition(
            "all_test_rows",
            pd.Series(True, index=comparison.index),
            "Todas las observaciones del test.",
        ),
        SegmentDefinition(
            "normal_days",
            ~special_flags,
            "Dias sin festivo, entorno de festivo, Semana Santa, evento ni meteo adversa codificada.",
        ),
        SegmentDefinition("holidays", comparison["is_holiday"], "Festivos codificados."),
        SegmentDefinition(
            "preholidays",
            comparison["is_preholiday"],
            "Dias inmediatamente anteriores a festivo.",
        ),
        SegmentDefinition(
            "postholidays",
            comparison["is_postholiday"],
            "Dias inmediatamente posteriores a festivo.",
        ),
        SegmentDefinition(
            "semana_santa",
            comparison["is_semana_santa"],
            "Dias de Semana Santa detectados por nombre de festivo.",
        ),
        SegmentDefinition(
            "event_days",
            comparison["event_day"],
            "Dias con eventos planificados mapeados a la serie.",
        ),
        SegmentDefinition(
            "high_impact_event_days",
            comparison["high_impact_event_day"],
            "Dias con eventos planificados de alto impacto.",
        ),
        SegmentDefinition(
            "bad_weather_days",
            comparison["bad_weather_day"],
            "Dias con meteorologia adversa codificada.",
        ),
        SegmentDefinition(
            "heavy_rain_days",
            comparison["heavy_rain_day"],
            "Dias con lluvia intensa codificada.",
        ),
        SegmentDefinition(
            "top_baseline_deviation_days",
            comparison["target_date"].isin(top_deviation_dates),
            "Top N dias de test con mayor desviacion agregada frente al baseline estacional.",
        ),
        SegmentDefinition(
            "top_tabular_worse_than_baseline_days",
            comparison["target_date"].isin(top_tabular_worse_dates),
            "Top N dias de test donde el tabular estricto empeora mas al baseline estacional.",
        ),
    ]


def build_tfm_main_results_summary(
    settings: Settings,
    *,
    series_policy: str = "all_series",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    strict_variant = str(settings["daily_modeling"]["target_variant_primary"])
    specs = [
        (
            "baseline",
            "Naive simple",
            "baseline_naive_simple",
            strict_variant,
            "all_series",
        ),
        (
            "baseline",
            "Naive estacional",
            "baseline_naive_seasonal_weekly",
            strict_variant,
            "all_series",
        ),
        (
            "proposed",
            "Tabular propuesto",
            "tabular_hgbr",
            strict_variant,
            series_policy,
        ),
        (
            "scenario",
            "Tabular forecastable",
            "tabular_hgbr",
            "forecastable_scenario",
            series_policy,
        ),
    ]

    for horizon_days in settings["daily_modeling"]["horizons"]:
        for model_role, model_label, model_name, variant, policy in specs:
            predictions = _load_predictions(
                settings,
                model_name=model_name,
                variant=variant,
                series_policy=policy,
                horizon_days=int(horizon_days),
            )
            test_predictions = predictions.loc[predictions["split_type"] == "test"].copy()
            rows.append(
                _result_summary_row(
                    test_predictions,
                    metric_level="serie_estacion_dia",
                    model_role=model_role,
                    model_label=model_label,
                    model_name=model_name,
                    variant=variant,
                    series_policy=policy,
                    horizon_days=int(horizon_days),
                )
            )
            network = test_predictions.groupby("target_date", dropna=False)[["y_true", "y_pred"]].sum().reset_index()
            rows.append(
                _result_summary_row(
                    network,
                    metric_level="dia_red",
                    model_role=model_role,
                    model_label=model_label,
                    model_name=model_name,
                    variant=variant,
                    series_policy=policy,
                    horizon_days=int(horizon_days),
                )
            )
    output = pd.DataFrame(rows)
    level_order = {"serie_estacion_dia": 0, "dia_red": 1}
    role_order = {"baseline": 0, "proposed": 1, "scenario": 2}
    label_order = {
        "Naive simple": 0,
        "Naive estacional": 1,
        "Tabular propuesto": 2,
        "Tabular forecastable": 3,
    }
    return (
        output.assign(
            _level_order=output["metric_level"].map(level_order),
            _role_order=output["model_role"].map(role_order),
            _label_order=output["model_label"].map(label_order),
        )
        .sort_values(["_level_order", "horizon_days", "_role_order", "_label_order"])
        .drop(columns=["_level_order", "_role_order", "_label_order"])
        .reset_index(drop=True)
    )


def build_external_variable_availability_summary(
    comparison: pd.DataFrame,
) -> pd.DataFrame:
    context = comparison.drop_duplicates(["target_date", "series_id"]).copy()
    specs = [
        {
            "variable_group": "calendario_festivos_semana_santa",
            "coverage_columns": [
                "calendar_is_holiday",
                "calendar_is_preholiday",
                "calendar_is_postholiday",
            ],
            "positive_columns": [
                "calendar_is_holiday",
                "calendar_is_preholiday",
                "calendar_is_postholiday",
                "is_semana_santa",
            ],
            "source": "external_daily_features",
            "availability": "disponible antes de predecir",
            "model_usage": "strict_available y forecastable_scenario",
            "granularity": "dia-red, replicado a serie",
            "leakage_risk": "bajo si procede de calendario oficial",
        },
        {
            "variable_group": "eventos_planificados",
            "coverage_columns": [
                "event_active_count",
                "event_starting_count",
                "event_ending_count",
            ],
            "positive_columns": [
                "event_active_count",
                "event_starting_count",
                "event_ending_count",
            ],
            "source": "events_phase2a_series_daily",
            "availability": "forecast/escenario",
            "model_usage": "solo forecastable_scenario",
            "granularity": "dia-linea-estacion",
            "leakage_risk": "medio si el calendario se completa a posteriori",
        },
        {
            "variable_group": "aforo_estimado",
            "coverage_columns": [
                "event_starting_estimated_attendance_sum",
                "event_starting_unknown_attendance_count",
            ],
            "positive_columns": [
                "event_starting_estimated_attendance_sum",
                "event_starting_unknown_attendance_count",
            ],
            "source": "events_phase2a_series_daily",
            "availability": "forecast/hipotesis explicita",
            "model_usage": "solo forecastable_scenario",
            "granularity": "dia-linea-estacion",
            "leakage_risk": "medio-alto si el aforo usado no estaba previsto",
        },
        {
            "variable_group": "eventos_por_estacion_serie",
            "coverage_columns": [
                "event_active_count",
                "event_high_impact_starting_count",
            ],
            "positive_columns": [
                "event_active_count",
                "event_high_impact_starting_count",
            ],
            "source": "events_phase2a_series_daily",
            "availability": "forecast/escenario",
            "model_usage": "solo forecastable_scenario",
            "granularity": "dia-linea-estacion",
            "leakage_risk": "medio por dependencias de mapeo y carga previa",
        },
        {
            "variable_group": "meteorologia",
            "coverage_columns": [
                "weather_is_bad_weather_day",
                "weather_is_heavy_rain_day",
                "weather_precip_mm",
                "weather_rain_hours",
            ],
            "positive_columns": [
                "weather_is_bad_weather_day",
                "weather_is_heavy_rain_day",
                "weather_precip_mm",
                "weather_rain_hours",
            ],
            "source": "external_daily_features",
            "availability": "forecast o escenario; observado es posteriori",
            "model_usage": "solo forecastable_scenario",
            "granularity": "dia-red, replicado a serie",
            "leakage_risk": "alto si se usa meteorologia observada como forecast",
        },
        {
            "variable_group": "servicio_planificado",
            "coverage_columns": [
                "service_duration_minutes",
                "service_has_planned_xml",
                "service_planned_code",
            ],
            "positive_columns": [
                "service_duration_minutes",
                "service_has_planned_xml",
            ],
            "source": "services_line_daily",
            "availability": "planificacion previa",
            "model_usage": "solo forecastable_scenario",
            "granularity": "dia-linea",
            "leakage_risk": "bajo-medio si se mantiene planificado, no ejecutado",
        },
        {
            "variable_group": "incidencias_y_servicio_ejecutado",
            "coverage_columns": [],
            "positive_columns": [],
            "source": "incidents_daily / used_service_xml_name",
            "availability": "solo a posteriori",
            "model_usage": "excluido del modelo principal",
            "granularity": "operativa ejecutada",
            "leakage_risk": "alto",
        },
    ]

    rows: list[dict[str, Any]] = []
    for spec in specs:
        coverage_columns = [column for column in spec["coverage_columns"] if column in context.columns]
        positive_columns = [column for column in spec["positive_columns"] if column in context.columns]
        if coverage_columns:
            coverage_ratio = float(context[coverage_columns].notna().all(axis=1).mean())
        else:
            coverage_ratio = np.nan
        if positive_columns:
            positive_mask = _numeric_positive_any(context, positive_columns)
            positive_row_count = int(positive_mask.sum())
            positive_day_count = int(context.loc[positive_mask, "target_date"].drop_duplicates().shape[0])
        else:
            positive_row_count = 0
            positive_day_count = 0
        rows.append(
            {
                "variable_group": spec["variable_group"],
                "source": spec["source"],
                "availability": spec["availability"],
                "model_usage": spec["model_usage"],
                "granularity": spec["granularity"],
                "coverage_ratio_test_rows": coverage_ratio,
                "positive_row_count": positive_row_count,
                "positive_day_count": positive_day_count,
                "leakage_risk": spec["leakage_risk"],
            }
        )
    return pd.DataFrame(rows)


def render_special_day_report(
    *,
    comparison: pd.DataFrame,
    segment_metrics: pd.DataFrame,
    top_rows: pd.DataFrame,
    main_results: pd.DataFrame,
    availability_summary: pd.DataFrame,
    artifact_paths: dict[str, Path],
) -> str:
    strict_rows = main_results.loc[
        (main_results["metric_level"] == "serie_estacion_dia") & (main_results["model_label"] == "Tabular propuesto")
    ]
    baseline_rows = main_results.loc[
        (main_results["metric_level"] == "serie_estacion_dia") & (main_results["model_label"] == "Naive estacional")
    ]
    scenario_rows = main_results.loc[
        (main_results["metric_level"] == "serie_estacion_dia") & (main_results["model_label"] == "Tabular forecastable")
    ]
    strict_wape_by_horizon = strict_rows.set_index("horizon_days")["wape"].to_dict()
    baseline_wape_by_horizon = baseline_rows.set_index("horizon_days")["wape"].to_dict()
    scenario_wape_by_horizon = scenario_rows.set_index("horizon_days")["wape"].to_dict()

    top_network = _format_top_rows_for_memory(top_rows.loc[top_rows["analysis_scope"] == "network_day"].copy()).head(12)
    segment_preview = _format_segment_metrics_for_memory(segment_metrics)

    h1_strict_gain = _percentage(
        _relative_improvement(
            baseline_wape_by_horizon.get(1, np.nan),
            strict_wape_by_horizon.get(1, np.nan),
        )
    )
    h7_strict_gain = _percentage(
        _relative_improvement(
            baseline_wape_by_horizon.get(7, np.nan),
            strict_wape_by_horizon.get(7, np.nan),
        )
    )
    h1_scenario_gain = _percentage(
        _relative_improvement(
            strict_wape_by_horizon.get(1, np.nan),
            scenario_wape_by_horizon.get(1, np.nan),
        )
    )
    h7_scenario_gain = _percentage(
        _relative_improvement(
            strict_wape_by_horizon.get(7, np.nan),
            scenario_wape_by_horizon.get(7, np.nan),
        )
    )

    top_dates = (
        top_rows.loc[
            (top_rows["analysis_scope"] == "network_day")
            & (top_rows["rank_type"] == "baseline_seasonal_deviation")
            & (top_rows["horizon_days"] == 1)
        ]
        .head(6)["target_date"]
        .dt.strftime("%Y-%m-%d")
        .tolist()
    )

    return "\n".join(
        [
            "# Analisis de dias especiales y desviaciones",
            "",
            "## Alcance",
            "",
            "- Unidad de evaluacion principal: observacion diaria `linea + estacion` en test.",
            "- La comparacion principal es `baseline_naive_seasonal_weekly` frente a `tabular_hgbr + strict_available`.",
            "- `forecastable_scenario` se mantiene como escenario de analisis: usa eventos, meteorologia y servicio planificado solo si existen como forecast, planificacion o hipotesis explicita.",
            "- Las variables externas se usan aqui tambien para segmentar errores de `strict_available`; eso no implica que hayan sido usadas como inputs por ese modelo.",
            "",
            "## Puntos de control",
            "",
            "1. Los mayores errores agregados frente al baseline estacional se concentran en festivos y cambios fuertes de patron: "
            + ", ".join(top_dates)
            + ".",
            "2. Esos errores son explicables sobre todo por calendario, festivos y Semana Santa; eventos y meteorologia aportan segmentos utiles, pero con menos cobertura positiva.",
            f"3. `strict_available` mejora el WAPE del baseline estacional en {h1_strict_gain} para D+1 y {h7_strict_gain} para D+7 a nivel serie-estacion-dia.",
            f"4. `forecastable_scenario` mejora adicionalmente a `strict_available` en {h1_scenario_gain} para D+1 y {h7_scenario_gain} para D+7, pero depende de variables que no deben asumirse disponibles en operativa sin feed o escenario.",
            "5. No se recomienda entrenar todavia un residual/uplift como modelo principal: las desviaciones fuertes ya mejoran mucho con el tabular directo, y el fallo pendiente mas claro son dias donde el baseline acierta y el tabular sobrecorrige.",
            "6. Recomendacion actual: mantener `strict_available` como variante operativa principal, mantener `forecastable_scenario` como analisis de escenarios y priorizar features/calidad externa antes que otro modelo.",
            "",
            "## Metricas principales",
            "",
            render_main_results_markdown(main_results),
            "",
            "## Segmentos",
            "",
            dataframe_to_markdown(segment_preview),
            "",
            "## Top desviaciones agregadas",
            "",
            dataframe_to_markdown(top_network),
            "",
            "## Variables externas",
            "",
            dataframe_to_markdown(availability_summary),
            "",
            "## Implicaciones",
            "",
            "- El baseline estacional falla de forma clara cuando un dia rompe el patron semanal normal. El tabular ya corrige gran parte de ese salto con calendario y autoregresivos.",
            "- Los eventos de alto impacto y la meteorologia adversa deben seguir como variables de escenario hasta confirmar que existen previsiones fiables antes de inferencia.",
            "- `incidents_daily` y `used_service_xml_name` deben mantenerse fuera del modelo principal porque describen ejecucion observada, no informacion disponible antes de predecir.",
            "- Si se incorporan reglas nuevas, deben entrar primero en el preprocesamiento/foundation y despues propagarse a entrenamiento, evaluacion e inferencia; no deben aparecer solo en notebooks.",
            "",
            "## Artefactos generados",
            "",
            *[f"- `{name}`: `{path.as_posix()}`" for name, path in artifact_paths.items()],
        ]
    )


def render_main_results_markdown(frame: pd.DataFrame) -> str:
    sections = []
    ordered_levels = ["serie_estacion_dia", "dia_red"]
    for metric_level in ordered_levels:
        group = frame.loc[frame["metric_level"] == metric_level].copy()
        if group.empty:
            continue
        title = (
            "Nivel observacion serie-estacion-dia" if metric_level == "serie_estacion_dia" else "Nivel agregado dia-red"
        )
        columns = [
            "model_label",
            "horizon",
            "variant",
            "mae",
            "rmse",
            "wape",
            "smape",
            "row_count",
        ]
        sections.extend(
            [
                f"### {title}",
                "",
                dataframe_to_markdown(group[columns].reset_index(drop=True)),
                "",
            ]
        )
    return "\n".join(sections).rstrip()


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_sin filas_"
    headers = [str(column) for column in frame.columns]
    rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for record in frame.itertuples(index=False):
        rows.append("| " + " | ".join(_format_markdown_value(value) for value in record) + " |")
    return "\n".join(rows)


def _load_horizon_comparison(
    settings: Settings,
    horizon_days: int,
    *,
    series_policy: str,
) -> pd.DataFrame:
    baseline = _load_predictions(
        settings,
        model_name="baseline_naive_seasonal_weekly",
        variant="strict_available",
        series_policy=series_policy,
        horizon_days=horizon_days,
    )
    strict = _load_predictions(
        settings,
        model_name="tabular_hgbr",
        variant="strict_available",
        series_policy=series_policy,
        horizon_days=horizon_days,
    )
    forecastable = _load_predictions(
        settings,
        model_name="tabular_hgbr",
        variant="forecastable_scenario",
        series_policy=series_policy,
        horizon_days=horizon_days,
    )
    baseline = baseline.loc[baseline["split_type"] == "test"].copy()
    strict = strict.loc[strict["split_type"] == "test"].copy()
    forecastable = forecastable.loc[forecastable["split_type"] == "test"].copy()

    merged = baseline[
        [
            *PREDICTION_KEYS,
            "series_label",
            "station_abbrev",
            "y_true",
            "y_pred",
        ]
    ].rename(columns={"y_pred": "y_pred_seasonal"})
    merged = merged.merge(
        strict[[*PREDICTION_KEYS, "y_pred"]].rename(columns={"y_pred": "y_pred_tabular_strict"}),
        how="inner",
        on=PREDICTION_KEYS,
        validate="1:1",
    )
    merged = merged.merge(
        forecastable[[*PREDICTION_KEYS, "y_pred"]].rename(columns={"y_pred": "y_pred_tabular_forecastable"}),
        how="inner",
        on=PREDICTION_KEYS,
        validate="1:1",
    )
    context = _load_context(settings, horizon_days, series_policy=series_policy)
    merged = merged.merge(
        context,
        how="left",
        on=["forecast_origin_date", "target_date", "series_id"],
        validate="1:1",
    )
    merged = _add_segment_flags(merged)
    return add_error_columns(merged)


def _load_predictions(
    settings: Settings,
    *,
    model_name: str,
    variant: str,
    series_policy: str,
    horizon_days: int,
) -> pd.DataFrame:
    predictions_path = (
        get_path(settings, "daily_modeling_predictions_dir")
        / f"{model_name}__{variant}__{series_policy}__h{horizon_days}.parquet"
    )
    if not predictions_path.exists():
        raise FileNotFoundError(f"Prediction artifact not found: '{predictions_path}'.")
    return pd.read_parquet(predictions_path)


def _load_context(
    settings: Settings,
    horizon_days: int,
    *,
    series_policy: str,
) -> pd.DataFrame:
    training_dir = get_path(settings, "daily_training_data_dir")
    context_path = training_dir / f"daily_training__forecastable_scenario__{series_policy}__h{horizon_days}.parquet"
    if not context_path.exists():
        context_path = training_dir / f"daily_training__strict_available__{series_policy}__h{horizon_days}.parquet"
    context = pd.read_parquet(context_path)
    columns = [column for column in CONTEXT_COLUMNS if column in context.columns]
    return context[columns].copy()


def _add_segment_flags(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["is_holiday"] = _as_bool(
        output.get("calendar_is_holiday", False),
        index=output.index,
    )
    output["is_preholiday"] = _as_bool(
        output.get("calendar_is_preholiday", False),
        index=output.index,
    )
    output["is_postholiday"] = _as_bool(
        output.get("calendar_is_postholiday", False),
        index=output.index,
    )
    holiday_name = (
        output.get("calendar_holiday_name", pd.Series("", index=output.index))
        .fillna("")
        .astype(str)
        .map(_normalize_text)
    )
    explicit_semana_santa = holiday_name.str.contains(
        "semana santa|jueves santo|viernes santo|domingo de ramos|lunes santo|martes santo|miercoles santo",
        regex=True,
    )
    output["is_semana_santa"] = _derive_semana_santa_mask(output, holiday_name) | explicit_semana_santa
    output["event_day"] = _numeric_positive_any(
        output,
        ["event_active_count", "event_starting_count", "event_ending_count"],
    )
    output["high_impact_event_day"] = _numeric_positive_any(
        output,
        [
            "event_high_impact_starting_count",
        ],
    )
    output["bad_weather_day"] = _as_bool(
        output.get("weather_is_bad_weather_day", False),
        index=output.index,
    )
    output["heavy_rain_day"] = _as_bool(
        output.get("weather_is_heavy_rain_day", False),
        index=output.index,
    )
    for column in SEGMENT_FLAG_COLUMNS:
        output[column] = output[column].map(bool).astype(object)
    return output


def _prefixed_metrics(
    frame: pd.DataFrame,
    prefix: str,
    prediction_column: str,
) -> dict[str, Any]:
    metrics = _compute_metrics(frame, prediction_column=prediction_column)
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def _compute_metrics(
    frame: pd.DataFrame,
    *,
    prediction_column: str,
) -> dict[str, Any]:
    available = frame.loc[frame["y_true"].notna() & frame[prediction_column].notna()].copy()
    if available.empty:
        return {
            "available_prediction_count": 0,
            "mae": np.nan,
            "rmse": np.nan,
            "wape": np.nan,
            "smape": np.nan,
            "abs_error_sum": np.nan,
        }

    error = available[prediction_column] - available["y_true"]
    abs_error = error.abs()
    denominator = float(available["y_true"].abs().sum())
    smape_denominator = available["y_true"].abs() + available[prediction_column].abs()
    smape_components = np.where(
        smape_denominator == 0,
        0.0,
        2.0 * abs_error / smape_denominator,
    )
    return {
        "available_prediction_count": int(len(available)),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt(np.mean(np.square(error)))),
        "wape": float(abs_error.sum() / denominator) if denominator else np.nan,
        "smape": float(np.mean(smape_components)),
        "abs_error_sum": float(abs_error.sum()),
    }


def _aggregate_network_days(frame: pd.DataFrame) -> pd.DataFrame:
    aggregations: dict[str, Any] = {
        "y_true": ("y_true", "sum"),
        "y_pred_seasonal": ("y_pred_seasonal", "sum"),
        "y_pred_tabular_strict": ("y_pred_tabular_strict", "sum"),
        "y_pred_tabular_forecastable": ("y_pred_tabular_forecastable", "sum"),
    }
    for column in SEGMENT_FLAG_COLUMNS:
        aggregations[column] = (column, "max")
    context_columns = [
        "calendar_holiday_name",
        "calendar_holiday_scope",
        "event_active_count",
        "event_high_impact_starting_count",
        "event_starting_estimated_attendance_sum",
        "weather_precip_mm",
        "weather_rain_hours",
    ]
    for column in context_columns:
        if column in frame.columns:
            if pd.api.types.is_numeric_dtype(frame[column]):
                aggregations[column] = (column, "sum")
            else:
                aggregations[column] = (column, _join_unique_values)
    network = frame.groupby(["horizon_days", "target_date"], dropna=False).agg(**aggregations).reset_index()
    for column in SEGMENT_FLAG_COLUMNS:
        network[column] = network[column].map(bool).astype(object)
    return network


def _select_ranked_rows(
    frame: pd.DataFrame,
    *,
    analysis_scope: str,
    rank_type: str,
    sort_column: str,
    top_n: int,
) -> pd.DataFrame:
    ranked = frame.copy()
    if rank_type == "tabular_strict_worse_than_seasonal":
        ranked = ranked.loc[ranked[sort_column] > 0].copy()
    ranked = ranked.sort_values(sort_column, ascending=False).head(top_n).copy()
    ranked["analysis_scope"] = analysis_scope
    ranked["rank_type"] = rank_type
    ranked["rank_position"] = range(1, len(ranked) + 1)
    output_columns = [
        "analysis_scope",
        "rank_type",
        "rank_position",
        "horizon_days",
        "target_date",
        "series_id",
        "series_label",
        "station_abbrev",
        "linea",
        "estacion",
        "is_holiday",
        "is_preholiday",
        "is_postholiday",
        "is_semana_santa",
        "event_day",
        "high_impact_event_day",
        "bad_weather_day",
        "heavy_rain_day",
        "y_true",
        "y_pred_seasonal",
        "y_pred_tabular_strict",
        "y_pred_tabular_forecastable",
        "seasonal_abs_error",
        "seasonal_relative_error",
        "seasonal_wape_contribution",
        "real_baseline_ratio",
        "real_minus_baseline",
        "tabular_strict_abs_error",
        "tabular_strict_error_delta_vs_seasonal",
        "tabular_strict_improves_vs_seasonal",
        "tabular_forecastable_abs_error",
        "forecastable_error_delta_vs_strict",
    ]
    for column in output_columns:
        if column not in ranked.columns:
            ranked[column] = np.nan
    return ranked[output_columns]


def _result_summary_row(
    frame: pd.DataFrame,
    *,
    metric_level: str,
    model_role: str,
    model_label: str,
    model_name: str,
    variant: str,
    series_policy: str,
    horizon_days: int,
) -> dict[str, Any]:
    metrics = _compute_metrics(frame, prediction_column="y_pred")
    return {
        "metric_level": metric_level,
        "model_role": model_role,
        "model_label": model_label,
        "model_name": model_name,
        "variant": variant,
        "series_policy": series_policy,
        "horizon_days": int(horizon_days),
        "horizon": f"D+{horizon_days}",
        "mae": metrics["mae"],
        "rmse": metrics["rmse"],
        "wape": metrics["wape"],
        "smape": metrics["smape"],
        "row_count": int(len(frame)),
    }


def _format_segment_metrics_for_memory(segment_metrics: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "horizon_days",
        "segment_name",
        "row_count",
        "baseline_seasonal_mae",
        "baseline_seasonal_rmse",
        "baseline_seasonal_wape",
        "baseline_seasonal_smape",
        "tabular_strict_mae",
        "tabular_strict_rmse",
        "tabular_strict_wape",
        "tabular_strict_smape",
        "tabular_strict_relative_wape_improvement_vs_seasonal",
        "tabular_forecastable_wape",
        "forecastable_relative_wape_improvement_vs_strict",
    ]
    return segment_metrics[columns].copy()


def _format_top_rows_for_memory(top_rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "analysis_scope",
        "rank_type",
        "rank_position",
        "horizon_days",
        "target_date",
        "series_label",
        "station_abbrev",
        "is_holiday",
        "is_semana_santa",
        "event_day",
        "bad_weather_day",
        "y_true",
        "y_pred_seasonal",
        "y_pred_tabular_strict",
        "seasonal_abs_error",
        "seasonal_relative_error",
        "seasonal_wape_contribution",
        "real_baseline_ratio",
        "real_minus_baseline",
        "tabular_strict_error_delta_vs_seasonal",
    ]
    available_columns = [column for column in columns if column in top_rows.columns]
    return top_rows[available_columns].copy()


def _top_target_dates(
    top_rows: pd.DataFrame,
    *,
    rank_type: str,
    analysis_scope: str,
) -> set[pd.Timestamp]:
    dates = top_rows.loc[
        (top_rows["rank_type"] == rank_type) & (top_rows["analysis_scope"] == analysis_scope),
        "target_date",
    ]
    return {pd.Timestamp(value) for value in dates.dropna().unique()}


def _relative_improvement(reference: float, candidate: float) -> float:
    if pd.isna(reference) or pd.isna(candidate) or abs(reference) <= EPSILON:
        return np.nan
    return float((reference - candidate) / reference)


def _percentage(value: float) -> str:
    if pd.isna(value):
        return "n/d"
    return f"{value:.1%}"


def _as_bool(value: Any, *, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        series = value.reindex(index, fill_value=False)
    else:
        series = pd.Series(value, index=index)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0.0).astype(float).astype(bool)
    return series.fillna(False).astype(bool)


def _normalize_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value).lower()
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _derive_semana_santa_mask(frame: pd.DataFrame, holiday_name: pd.Series) -> pd.Series:
    if "target_date" not in frame.columns:
        return pd.Series(False, index=frame.index)
    target_dates = pd.to_datetime(frame["target_date"]).dt.normalize()
    holy_dates: set[pd.Timestamp] = set()

    jueves_santo_dates = target_dates.loc[holiday_name.str.contains("jueves santo", regex=False)].dropna()
    viernes_santo_dates = target_dates.loc[holiday_name.str.contains("viernes santo", regex=False)].dropna()

    for date in jueves_santo_dates.unique():
        base = pd.Timestamp(date)
        holy_dates.update(pd.date_range(base - pd.Timedelta(days=4), periods=9))
    for date in viernes_santo_dates.unique():
        base = pd.Timestamp(date)
        holy_dates.update(pd.date_range(base - pd.Timedelta(days=5), periods=9))

    if not holy_dates:
        return pd.Series(False, index=frame.index)
    return target_dates.isin(holy_dates)


def _numeric_positive_any(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    available_columns = [column for column in columns if column in frame.columns]
    if not available_columns:
        return pd.Series(False, index=frame.index)
    numeric = frame[available_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return numeric.gt(0).any(axis=1)


def _join_unique_values(values: pd.Series) -> str:
    unique_values = [str(value) for value in values.dropna().unique().tolist() if str(value).strip()]
    return ", ".join(sorted(unique_values))


def _format_markdown_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.4f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _update_memory_asset_manifest(
    project_root: Path,
    *,
    memory_tables_dir: Path,
    table_paths: dict[str, Path],
) -> None:
    manifest_path = memory_tables_dir.parent / "asset_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"figures": {}, "tables": {}}
    manifest.setdefault("tables", {})
    for key, path in table_paths.items():
        manifest["tables"][key] = str(path.relative_to(project_root))
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
