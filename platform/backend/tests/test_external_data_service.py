from __future__ import annotations

from datetime import date

import pandas as pd

from metro_scenario_studio.core.config import Settings
from metro_scenario_studio.services.external_data import ExternalDataService


def test_external_data_reads_weather_from_monorepo_data_root(tmp_path) -> None:
    data_root = tmp_path / "data"
    feature_dir = data_root / "processed" / "external_features"
    feature_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "date": "2026-06-18",
                "temp_mean_c": 28.5,
                "temp_min_c": 21.0,
                "temp_max_c": 33.0,
                "precip_mm": 4.2,
                "rain_hours": 2.0,
                "wind_mean_kmh": 14.0,
                "humidity_mean_pct": 62.0,
                "weather_code": "rain",
                "is_rainy_day": True,
                "is_heavy_rain_day": False,
                "is_hot_day": True,
                "is_cold_day": False,
                "is_bad_weather_day": True,
                "weather_source": "open_meteo_test",
                "is_holiday": False,
                "is_preholiday": False,
                "is_postholiday": False,
                "day_of_week": 4,
            }
        ]
    ).to_parquet(feature_dir / "external_daily_features.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        data_root=data_root,
        metro_demand_models_root=tmp_path / "ml_pipeline",
    )

    snapshot = ExternalDataService(settings).get_snapshot(date(2026, 6, 18), date(2026, 6, 18))

    assert snapshot.coverage.weather_days == 1
    assert snapshot.weather[0].source == "open_meteo_test"
    assert snapshot.weather[0].temp_mean == 28.5
    assert snapshot.weather[0].rain is True


def test_external_data_reads_events_from_monorepo_data_root(tmp_path) -> None:
    data_root = tmp_path / "data"
    events_dir = data_root / "interim" / "operations"
    events_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "event_id": "evt-1",
                "title": "Concierto puerto",
                "start_date": "2026-06-20",
                "end_date": "2026-06-21",
                "start_ts": "2026-06-20 20:00:00",
                "end_ts": "2026-06-20 23:00:00",
                "category": "cultura",
                "attendance_estimated": 7000,
                "comments": "Importado desde calendario externo",
            }
        ]
    ).to_parquet(events_dir / "events_normalized.parquet")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        sqlite_path=tmp_path / "storage" / "metro_scenario_studio.db",
        data_root=data_root,
        metro_demand_models_root=tmp_path / "ml_pipeline",
    )

    snapshot = ExternalDataService(settings).get_snapshot(date(2026, 6, 20), date(2026, 6, 20))

    assert snapshot.coverage.event_days == 1
    assert snapshot.events[0].name == "Concierto puerto"
    assert snapshot.events[0].source == "events_normalized.parquet"
