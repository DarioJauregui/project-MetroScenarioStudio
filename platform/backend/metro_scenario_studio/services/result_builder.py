from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd

from metro_scenario_studio.domain.schemas import PredictionRow, ScenarioExecution
from metro_scenario_studio.services.stations import load_station_catalog

if TYPE_CHECKING:
    from metro_scenario_studio.core.config import Settings

logger = logging.getLogger(__name__)


def rows_from_frame(
    frame: pd.DataFrame,
    execution: ScenarioExecution,
    *,
    prediction_mode: str,
    settings: Settings,
) -> list[PredictionRow]:
    if frame.empty or "target_date" not in frame.columns or "y_pred" not in frame.columns:
        return []
    frame = frame.copy()
    frame["target_date"] = pd.to_datetime(frame["target_date"]).dt.date
    frame = frame[(frame["target_date"] >= execution.range_start) & (frame["target_date"] <= execution.range_end)]
    if "model_variant" in frame.columns:
        frame = frame[frame["model_variant"] == execution.model_variant]
    elif "variant" in frame.columns:
        frame = frame[frame["variant"] == execution.model_variant]
    if "model_name" in frame.columns:
        frame = frame[frame["model_name"] == execution.model_name]
    if frame.empty:
        return []

    catalog = {
        str(station["series_id"]): station for station in load_station_catalog(settings.metro_demand_models_root)
    }
    rows: list[PredictionRow] = []
    for raw in frame.to_dict(orient="records"):
        target_date = raw["target_date"]
        series_id = str(_value(raw, "series_id", ""))
        station = catalog.get(series_id, {})
        y_pred = _as_float(raw.get("y_pred"))
        if y_pred is None:
            continue
        rows.append(
            PredictionRow(
                target_date=target_date,
                linea=str(_value(raw, "linea", station.get("linea", ""))),
                estacion=str(_value(raw, "estacion", raw.get("series_label", station.get("estacion", "")))),
                series_id=series_id,
                station_abbrev=str(
                    _value(raw, "station_abbrev", raw.get("series_label", station.get("station_abbrev", series_id)))
                ),
                network_order=int(_as_float(_value(raw, "network_order", station.get("network_order", 0))) or 0),
                y_pred=y_pred,
                y_real=_first_float(raw, ["y_true", "trip_count_target"]),
                model_variant=execution.model_variant,
                horizon_days=int(_as_float(raw.get("horizon_days")) or 1),
                forecast_origin_date=_as_date(raw.get("forecast_origin_date")),
                prediction_mode=prediction_mode,
            )
        )
    return rows


def deterministic_prediction(execution: ScenarioExecution, settings: Settings) -> list[PredictionRow]:
    stations = load_station_catalog(settings.metro_demand_models_root)
    rows: list[PredictionRow] = []
    current = execution.range_start
    while current <= execution.range_end:
        weekday_factor = 0.82 if current.weekday() >= 5 else 1.0
        scenario_factor = 1.035 if execution.model_variant == "forecastable_scenario" else 1.0
        for station in stations:
            order = int(station["network_order"])
            base = 850 + (order * 97)
            line_factor = 1.08 if station["linea"] == "LINEA 1" else 0.92
            y_pred = round(base * weekday_factor * scenario_factor * line_factor, 3)
            rows.append(
                PredictionRow(
                    target_date=current,
                    linea=str(station["linea"]),
                    estacion=str(station["estacion"]),
                    series_id=str(station["series_id"]),
                    station_abbrev=str(station["station_abbrev"]),
                    network_order=order,
                    y_pred=y_pred,
                    y_real=None,
                    model_variant=execution.model_variant,
                    horizon_days=1,
                )
            )
        current += timedelta(days=1)
    return rows


def _value(row: dict[str, Any], key: str, default: Any = None) -> Any:
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return value


def _as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(row: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _as_float(row.get(key))
        if value is not None:
            return value
    return None


def _as_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None
