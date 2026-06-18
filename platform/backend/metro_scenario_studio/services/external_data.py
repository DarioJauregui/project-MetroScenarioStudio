from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from metro_scenario_studio.domain.rules import generate_range_warnings
from metro_scenario_studio.domain.schemas import (
    CalendarVariable,
    CoverageSummary,
    EventType,
    EventVariable,
    ExternalDataSnapshot,
    ImpactLevel,
    WeatherVariable,
)

if TYPE_CHECKING:
    from metro_scenario_studio.core.config import Settings


class ExternalDataService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_snapshot(self, start: date, end: date) -> ExternalDataSnapshot:
        dates = list(_date_range(start, end))
        real_features = self._read_external_daily_features(start, end)
        calendar = self._calendar(dates, real_features)
        events = self._planned_events(dates)
        weather = self._weather(dates, real_features)
        event_days = len({event.target_date for event in events})
        weather_days = len({item.target_date for item in weather})
        coverage = CoverageSummary(
            calendar_days=len(calendar),
            event_days=event_days,
            weather_days=weather_days,
            total_days=len(dates),
        )
        warnings = generate_range_warnings(
            start=start,
            end=end,
            coverage=coverage,
            reasonable_horizon_days=self.settings.reasonable_horizon_days,
            long_range_days=self.settings.long_range_days,
        )
        return ExternalDataSnapshot(
            range_start=start,
            range_end=end,
            calendar=calendar,
            events=events,
            weather=weather,
            coverage=coverage,
            warnings=warnings,
        )

    def _calendar(self, dates: list[date], real_features: dict[date, dict[str, Any]]) -> list[CalendarVariable]:
        calendar: list[CalendarVariable] = []
        for value in dates:
            real = real_features.get(value, {})
            calendar.append(
                CalendarVariable(
                    target_date=value,
                    day_of_week=int(real.get("day_of_week", value.weekday())),
                    is_holiday=_bool(real.get("is_holiday", False)),
                    is_preholiday=_bool(real.get("is_preholiday", False)),
                    is_postholiday=_bool(real.get("is_postholiday", False)),
                    is_bridge=False,
                    special_day=_string_or_none(real.get("holiday_name")),
                    source="external_daily_features" if real else "calendar_generated",
                )
            )
        return calendar

    def _planned_events(self, dates: list[date]) -> list[EventVariable]:
        real_events = self._read_events_normalized(min(dates), max(dates)) if dates else []
        if real_events:
            return real_events
        if not self.settings.use_mock_inference:
            return []
        events: list[EventVariable] = []
        for value in dates:
            if value.weekday() == 5:
                events.append(
                    EventVariable(
                        event_id=f"auto_event_{value.isoformat()}",
                        name="Actividad cultural planificada",
                        target_date=value,
                        event_type=EventType.CULTURAL,
                        impact_level=ImpactLevel.MEDIUM,
                        affected_stations=["all"],
                        comment="Evento sintetico de cobertura para MVP local.",
                        source="local_planning_snapshot",
                    )
                )
        return events

    def _weather(self, dates: list[date], real_features: dict[date, dict[str, Any]]) -> list[WeatherVariable]:
        weather: list[WeatherVariable] = []
        for value in dates:
            real = real_features.get(value)
            if real:
                weather.append(
                    WeatherVariable(
                        target_date=value,
                        rain=_bool(real.get("is_rainy_day", False)),
                        heavy_rain=_bool(real.get("is_heavy_rain_day", False)),
                        approx_temperature=_float_or_none(real.get("temp_mean_c")),
                        hot_day=_bool(real.get("is_hot_day", False)),
                        cold_day=_bool(real.get("is_cold_day", False)),
                        bad_weather=_bool(real.get("is_bad_weather_day", False)),
                        temp_min=_float_or_none(real.get("temp_min_c")),
                        temp_mean=_float_or_none(real.get("temp_mean_c")),
                        temp_max=_float_or_none(real.get("temp_max_c")),
                        precip_mm=_float_or_none(real.get("precip_mm")),
                        rain_hours=_float_or_none(real.get("rain_hours")),
                        wind=_float_or_none(real.get("wind_mean_kmh")),
                        humidity=_float_or_none(real.get("humidity_mean_pct")),
                        weather_code=_string_or_none(real.get("weather_code")),
                        alert_level=_alert_level(real),
                        alert_summary=_alert_summary(real),
                        source=str(real.get("weather_source") or "external_daily_features"),
                    )
                )
            elif self.settings.use_mock_inference and value <= date.today():
                weather.append(
                    WeatherVariable(
                        target_date=value,
                        rain=value.weekday() == 2,
                        heavy_rain=False,
                        approx_temperature=22.0,
                        temp_mean=22.0,
                        precip_mm=3.0 if value.weekday() == 2 else 0.0,
                        rain_hours=1.0 if value.weekday() == 2 else 0.0,
                        alert_level="sin_alerta",
                        alert_summary="Sin alerta meteorologica relevante.",
                        source="observed_or_cached",
                    )
                )
        return weather

    def _read_external_daily_features(self, start: date, end: date) -> dict[date, dict[str, Any]]:
        path = self.settings.data_root / "processed" / "external_features" / "external_daily_features.parquet"
        if not path.exists():
            path = self.settings.data_root / "interim" / "external_features" / "weather_daily.parquet"
        if not path.exists():
            return {}
        try:
            import pandas as pd

            frame = pd.read_parquet(path)
            date_column = "date"
            frame[date_column] = pd.to_datetime(frame[date_column]).dt.date
            frame = frame[(frame[date_column] >= start) & (frame[date_column] <= end)]
            return {row[date_column]: row.to_dict() for _, row in frame.iterrows()}
        except Exception:
            return {}

    def _read_events_normalized(self, start: date, end: date) -> list[EventVariable]:
        path = self.settings.data_root / "interim" / "operations" / "events_normalized.parquet"
        if not path.exists():
            return []
        try:
            import pandas as pd

            frame = pd.read_parquet(path)
            frame["start_date"] = pd.to_datetime(frame["start_date"]).dt.date
            frame["end_date"] = pd.to_datetime(frame["end_date"]).dt.date
            frame = frame[(frame["start_date"] <= end) & (frame["end_date"] >= start)]
            events: list[EventVariable] = []
            for _, row in frame.head(250).iterrows():
                target_date = max(row["start_date"], start)
                events.append(
                    EventVariable(
                        event_id=f"real_event_{row.get('event_id')}",
                        name=str(row.get("title") or "Evento"),
                        target_date=target_date,
                        start_time=_time_text(row.get("start_ts")),
                        end_time=_time_text(row.get("end_ts")),
                        event_type=_event_type(row.get("category")),
                        impact_level=_impact_level(row.get("attendance_estimated")),
                        affected_stations=["all"],
                        comment=_string_or_none(row.get("comments")),
                        source="events_normalized.parquet",
                    )
                )
            return events
        except Exception:
            return []


def _date_range(start: date, end: date):
    if end < start:
        raise ValueError("range_end must be greater than or equal to range_start")
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        import pandas as pd

        if pd.isna(value):
            return False
    except Exception:
        pass
    return bool(value)


def _float_or_none(value: Any) -> float | None:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _time_text(value: Any) -> str | None:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
        return pd.to_datetime(value).strftime("%H:%M")
    except Exception:
        return None


def _event_type(value: Any) -> EventType:
    text = str(value or "").lower()
    if "deport" in text:
        return EventType.SPORTS
    if "congreso" in text or "feria" in text:
        return EventType.CONGRESS
    if "relig" in text:
        return EventType.RELIGIOUS
    if "univers" in text:
        return EventType.UNIVERSITY
    if text:
        return EventType.CULTURAL
    return EventType.OTHER


def _impact_level(attendance: Any) -> ImpactLevel:
    value = _float_or_none(attendance) or 0
    if value >= 15000:
        return ImpactLevel.VERY_HIGH
    if value >= 5000:
        return ImpactLevel.HIGH
    if value >= 1000:
        return ImpactLevel.MEDIUM
    return ImpactLevel.LOW


def _alert_level(row: dict[str, Any]) -> str:
    explicit = _string_or_none(row.get("alert_level") or row.get("weather_alert_level"))
    if explicit:
        return explicit
    precip = _float_or_none(row.get("precip_mm")) or 0
    wind = _float_or_none(row.get("wind_max_kmh") or row.get("wind_mean_kmh")) or 0
    if precip >= 60 or wind >= 90:
        return "roja"
    if precip >= 30 or wind >= 70:
        return "naranja"
    if precip >= 15 or wind >= 50:
        return "amarilla"
    return "sin_alerta"


def _alert_summary(row: dict[str, Any]) -> str:
    level = _alert_level(row)
    if level == "sin_alerta":
        return "Sin alerta meteorologica relevante."
    pieces = []
    precip = _float_or_none(row.get("precip_mm"))
    wind = _float_or_none(row.get("wind_max_kmh") or row.get("wind_mean_kmh"))
    if precip is not None:
        pieces.append(f"precipitacion {precip:g} mm")
    if wind is not None:
        pieces.append(f"viento {wind:g} km/h")
    return f"Alerta {level}: {', '.join(pieces) if pieces else 'condiciones adversas'}."
