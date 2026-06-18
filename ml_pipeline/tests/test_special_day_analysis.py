from __future__ import annotations

import pandas as pd

from metro_demand_models.evaluation.special_days import (
    SegmentDefinition,
    build_top_deviation_rows,
    summarize_segments,
)


def test_summarize_segments_reports_model_improvements() -> None:
    frame = pd.DataFrame(
        {
            "horizon_days": [1, 1],
            "y_true": [100.0, 100.0],
            "y_pred_seasonal": [80.0, 100.0],
            "y_pred_tabular_strict": [90.0, 110.0],
            "y_pred_tabular_forecastable": [95.0, 100.0],
            "is_special": [True, False],
        }
    )

    metrics = summarize_segments(
        frame,
        [
            SegmentDefinition("all_rows", pd.Series([True, True], index=frame.index)),
            SegmentDefinition("special_rows", frame["is_special"]),
        ],
    )

    special = metrics.loc[metrics["segment_name"] == "special_rows"].iloc[0]
    assert special["row_count"] == 1
    assert special["baseline_seasonal_wape"] == 0.2
    assert special["tabular_strict_wape"] == 0.1
    assert special["tabular_forecastable_wape"] == 0.05
    assert special["tabular_strict_relative_wape_improvement_vs_seasonal"] == 0.5
    assert special["forecastable_relative_wape_improvement_vs_strict"] == 0.5


def test_build_top_deviation_rows_keeps_network_and_series_context() -> None:
    frame = pd.DataFrame(
        {
            "horizon_days": [1, 1, 1],
            "target_date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"]),
            "series_id": ["A", "B", "A"],
            "linea": ["LINEA 1", "LINEA 1", "LINEA 1"],
            "estacion": ["Alpha", "Beta", "Alpha"],
            "series_label": ["A", "B", "A"],
            "station_abbrev": ["A", "B", "A"],
            "calendar_is_holiday": [1.0, 1.0, 0.0],
            "calendar_is_preholiday": [0.0, 0.0, 0.0],
            "calendar_is_postholiday": [0.0, 0.0, 0.0],
            "is_semana_santa": [False, False, False],
            "event_day": [False, False, False],
            "high_impact_event_day": [False, False, False],
            "bad_weather_day": [False, False, False],
            "heavy_rain_day": [False, False, False],
            "y_true": [100.0, 80.0, 100.0],
            "y_pred_seasonal": [50.0, 80.0, 100.0],
            "y_pred_tabular_strict": [90.0, 70.0, 60.0],
            "y_pred_tabular_forecastable": [95.0, 75.0, 80.0],
        }
    )

    rows = build_top_deviation_rows(frame, top_n=1)

    scopes = set(rows["analysis_scope"])
    assert scopes == {"network_day", "series_day"}
    rank_types = set(rows["rank_type"])
    assert rank_types == {
        "baseline_seasonal_deviation",
        "tabular_strict_worse_than_seasonal",
    }

    top_series = rows.loc[
        (rows["analysis_scope"] == "series_day") & (rows["rank_type"] == "baseline_seasonal_deviation")
    ].iloc[0]
    assert top_series["series_id"] == "A"
    assert top_series["seasonal_abs_error"] == 50.0
    assert top_series["tabular_strict_improves_vs_seasonal"] is True
