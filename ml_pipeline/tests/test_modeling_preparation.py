from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from metro_demand_models.configuration import load_settings
from metro_demand_models.data import modeling
from metro_demand_models.data.modeling import (
    aggregate_trips_to_station_daily,
    build_service_date,
    build_network_changes_daily_context,
    ensure_external_daily_feature_coverage,
    filter_validation_rows_to_modeling_trips,
    normalize_validation_type,
    prepare_modeling_base_dataset,
    safe_left_join,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_external_daily_frame(dates: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for value in dates:
        date_value = pd.Timestamp(value)
        iso_week = date_value.isocalendar()
        rows.append(
            {
                "date": date_value,
                "year": int(date_value.year),
                "month": int(date_value.month),
                "day": int(date_value.day),
                "quarter": int(date_value.quarter),
                "week_of_year": int(iso_week.week),
                "day_of_year": int(date_value.day_of_year),
                "day_of_week": int(date_value.dayofweek + 1),
                "day_of_week_name": date_value.day_name(),
                "is_weekend": bool(date_value.dayofweek >= 5),
                "is_holiday": False,
                "holiday_name": "",
                "holiday_scope": "",
                "is_holiday_mmo": False,
                "is_preholiday": False,
                "is_postholiday": False,
                "days_to_next_holiday": 0.0,
                "days_since_prev_holiday": 0.0,
                "is_bridge_candidate": False,
                "is_month_start": bool(date_value.is_month_start),
                "is_month_end": bool(date_value.is_month_end),
                "temp_min_c": 10.0,
                "temp_max_c": 20.0,
                "temp_mean_c": 15.0,
                "precip_mm": 0.0,
                "rain_hours": 0,
                "wind_max_kmh": 5.0,
                "wind_mean_kmh": 2.0,
                "humidity_mean_pct": 60.0,
                "pressure_mean_hpa": 1015.0,
                "weather_code": 1,
                "weather_source": "aemet",
                "weather_summary": "clear",
                "is_rainy_day": False,
                "is_heavy_rain_day": False,
                "is_hot_day": False,
                "is_cold_day": False,
                "is_bad_weather_day": False,
                "events_total_count": 0,
                "events_high_impact_count": 0,
                "events_estimated_attendance_sum": 0,
                "events_unknown_attendance_count": 0,
                "events_near_metro_count": 0,
                "events_city_center_count": 0,
                "events_culture_count": 0,
                "events_sports_count": 0,
                "events_congress_count": 0,
                "events_university_count": 0,
                "events_religious_count": 0,
                "events_other_count": 0,
                "events_weighted_impact_sum": 0.0,
                "max_event_impact_score": 0.0,
                "has_major_event": False,
                "has_multiple_major_events": False,
                "events_geocoded_count": 0,
                "events_unique_venue_count": 0,
                "run_id": "test-run",
                "year_month": date_value.strftime("%Y-%m"),
                "year_week": f"{date_value.year}-{int(iso_week.week):02d}",
            }
        )
    return pd.DataFrame(rows)


def _build_test_frames() -> dict[str, pd.DataFrame]:
    validations = pd.DataFrame(
        {
            "fecha_validacion": pd.to_datetime(
                [
                    "2026-01-01 08:10:00",
                    "2026-01-01 08:15:00",
                    "2026-01-01 09:00:00",
                    "2026-01-02 10:00:00",
                ]
            ).tz_localize("Europe/Madrid"),
            "linea": ["LINEA 1", "LINEA 1", "LINEA 1", "LINEA 2"],
            "estacion": ["Perchel", "Perchel", "Atarazanas", "La Isla"],
            "cod_eq": ["PCH-001", "PCH-002", "ATZ-001", "ISL-001"],
            "tipo_validacion": [
                "Primera entrada",
                "Primera entrada",
                "Primera salida",
                "Entrada multiviaje",
            ],
            "tipo_titulo": [
                "Monedero Metro Malaga",
                "Monedero Metro Malaga",
                "Billete ocasional",
                "Pase Gratuito",
            ],
            "id_tarjeta": ["No aplica"] * 4,
            "num_tarjeta": ["100", "101", "102", "103"],
            "dinero_deducido": [0.82, 0.82, None, 0.0],
            "saldo_restante": [2.68, 1.86, 1.0, None],
            "viajes_deducidos": [0.0, 0.0, None, 1.0],
            "fecha_validacion_hora_estimada": [False, True, False, False],
            "fecha_generacion": pd.to_datetime(
                [
                    "2026-01-01 23:50:00",
                    "2026-01-01 23:50:00",
                    "2026-01-01 23:50:00",
                    "2026-01-02 23:50:00",
                ]
            ).tz_localize("Europe/Madrid"),
            "rango_desde": pd.to_datetime(
                [
                    "2026-01-01 00:00:00",
                    "2026-01-01 00:00:00",
                    "2026-01-01 00:00:00",
                    "2026-01-02 00:00:00",
                ]
            ).tz_localize("Europe/Madrid"),
            "rango_hasta": pd.to_datetime(
                [
                    "2026-01-01 23:59:00",
                    "2026-01-01 23:59:00",
                    "2026-01-01 23:59:00",
                    "2026-01-02 23:59:00",
                ]
            ).tz_localize("Europe/Madrid"),
            "dia": ["2026-01-01", "2026-01-01", "2026-01-01", "2026-01-02"],
            "archivo_origen": ["file_1.csv", "file_1.csv", "file_2.csv", "file_3.csv"],
            "_orden_manifest": [1, 1, 2, 3],
        }
    )

    stations_master = pd.DataFrame(
        {
            "linea": ["LINEA 1", "LINEA 2", "LINEA 1", "LINEA 2"],
            "estacion": ["Perchel", "Perchel", "Atarazanas", "La Isla"],
            "station_join_key": ["perchel", "perchel", "atarazanas", "la isla"],
            "station_display_name": ["El Perchel", "El Perchel", "Atarazanas", "La Isla"],
            "station_abbrev": ["PCH", "PCH", "ATZ", "ISL"],
            "network_order": [11, 11, 13, 14],
            "lat": [36.7140, 36.7140, 36.7177, 36.7112],
            "lon": [-4.4325, -4.4325, -4.4233, -4.4400],
            "zone": ["Perchel", "Perchel", "Centro", "Carretera de Cadiz"],
            "station_group": ["Perchel", "Perchel", "Atarazanas", "La Isla"],
            "is_interchange_candidate": [True, True, False, False],
            "station_reference_label": ["11_PCH", "11_PCH", "13_ATZ", "14_ISL"],
        }
    )

    lines_master = pd.DataFrame(
        {
            "linea": ["LINEA 1", "LINEA 2"],
            "line_reference_path": ["TCH -> ATZ", "ISL -> PDD"],
        }
    )

    equipment_master = pd.DataFrame(
        {
            "linea": ["LINEA 1", "LINEA 1", "LINEA 1", "LINEA 2"],
            "estacion": ["Perchel", "Perchel", "Atarazanas", "La Isla"],
            "cod_eq": ["PCH-001", "PCH-002", "ATZ-001", "ISL-001"],
            "is_suspect_code": [False, False, False, False],
            "is_significant_equipment": [True, True, True, True],
            "station_join_key": ["perchel", "perchel", "atarazanas", "la isla"],
            "station_display_name": ["El Perchel", "El Perchel", "Atarazanas", "La Isla"],
            "station_abbrev": ["PCH", "PCH", "ATZ", "ISL"],
            "network_order": [11, 11, 13, 14],
            "lat": [36.7140, 36.7140, 36.7177, 36.7112],
            "lon": [-4.4325, -4.4325, -4.4233, -4.4400],
            "zone": ["Perchel", "Perchel", "Centro", "Carretera de Cadiz"],
            "station_group": ["Perchel", "Perchel", "Atarazanas", "La Isla"],
            "station_reference_label": ["11_PCH", "11_PCH", "13_ATZ", "14_ISL"],
        }
    )

    network_changes = pd.DataFrame(
        {
            "change_type": ["equipment_first_seen", "line_station_first_seen"],
            "effective_date": ["2026-01-01", "2026-01-01"],
            "linea": ["LINEA 1", "LINEA 1"],
            "estacion": ["Perchel", "Perchel"],
            "cod_eq": ["PCH-001", None],
            "notes": ["Alta de equipo", "Alta de estación"],
        }
    )

    metro_stations = pd.DataFrame(
        {
            "data_station_name": ["Perchel", "Atarazanas", "La Isla"],
            "station_display_name": ["El Perchel", "Atarazanas", "La Isla"],
            "station_abbrev": ["PCH", "ATZ", "ISL"],
            "network_order": [11, 13, 14],
            "linea": ["LINEA 1|LINEA 2", "LINEA 1", "LINEA 2"],
            "lat": [36.7140, 36.7177, 36.7112],
            "lon": [-4.4325, -4.4233, -4.4400],
            "zone": ["Perchel", "Centro", "Carretera de Cadiz"],
            "station_group": ["Perchel", "Atarazanas", "La Isla"],
            "source_note": ["manual", "manual", "manual"],
        }
    )

    return {
        "validations": validations,
        "external_daily_features": _build_external_daily_frame(["2026-01-01", "2026-01-02"]),
        "stations_master": stations_master,
        "lines_master": lines_master,
        "equipment_master": equipment_master,
        "equipment_significant_master": equipment_master.assign(
            equipment_observation_status=["historical_or_review"] * 4
        ),
        "network_changes_history": network_changes,
        "metro_stations": metro_stations,
    }


class _FakeScanner:
    def __init__(self, dataframe: pd.DataFrame, columns: list[str], batch_size: int) -> None:
        self.dataframe = dataframe[columns].copy()
        self.batch_size = batch_size

    def to_batches(self):
        for start in range(0, len(self.dataframe), self.batch_size):
            yield pa.Table.from_pandas(
                self.dataframe.iloc[start : start + self.batch_size],
                preserve_index=False,
            )


class _FakeDataset:
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.dataframe = dataframe
        self.schema = pa.Table.from_pandas(
            dataframe,
            preserve_index=False,
        ).schema

    def scanner(self, *, columns: list[str], batch_size: int):
        return _FakeScanner(self.dataframe, columns, batch_size)


def test_aggregate_trips_to_station_daily_builds_expected_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = _build_test_frames()
    monkeypatch.setattr(
        modeling.ds,
        "dataset",
        lambda *args, **kwargs: _FakeDataset(frames["validations"]),
    )

    aggregated = aggregate_trips_to_station_daily("unused", batch_size=2)

    assert len(aggregated) == 1

    perchel_row = aggregated.loc[
        (aggregated["service_date"] == pd.Timestamp("2026-01-01"))
        & (aggregated["linea"] == "LINEA 1")
        & (aggregated["estacion"] == "Perchel")
    ].iloc[0]
    assert perchel_row["trip_count"] == 2
    assert perchel_row["raw_unique_equipment_count"] == 2
    assert perchel_row["raw_rows_with_estimated_time"] == 1
    assert perchel_row["raw_missing_money_fields_count"] == 0
    assert perchel_row["raw_missing_trip_fields_count"] == 0


def test_build_service_date_supports_configurable_operational_boundary() -> None:
    timestamps = pd.Series(pd.to_datetime(["2026-01-02 00:30:00", "2026-01-02 03:30:00"]).tz_localize("Europe/Madrid"))

    natural_day = build_service_date(timestamps)
    shifted_day = build_service_date(timestamps, boundary_hour=3)

    assert natural_day.tolist() == [
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-02"),
    ]
    assert shifted_day.tolist() == [
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-01-02"),
    ]


def test_filter_validation_rows_to_modeling_trips_normalizes_scope_and_titles() -> None:
    raw = pd.DataFrame(
        {
            "tipo_validacion": [
                "Primera entrada",
                "Primera salida",
                "Regularizaci?n en salida",
                "Regularizaci?n sencilla transbordo",
                "Transbordo multiviaje",
                "Entrada multiviaje",
                "Texto no reconocido",
            ],
            "tipo_titulo": [
                "Monedero Metro Malaga",
                "Billete ocasional",
                "MásMetro",
                "Titulo Promocional",
                "Pase Gratuito",
                "Monedero EMV",
                "Monedero ABT",
            ],
            "value": range(7),
        }
    )

    filtered = filter_validation_rows_to_modeling_trips(raw)

    assert filtered["value"].tolist() == [0, 2, 3, 5]
    assert filtered["tipo_validacion_normalizada"].tolist() == [
        "primera_entrada",
        "regularizacion_en_salida",
        "regularizacion_sencilla",
        "entrada_multiviaje",
    ]
    assert filtered["tipo_titulo_limpio"].tolist() == [
        "Monedero Metro Malaga",
        "MásMetro",
        "Título Promocional",
        "Monedero EMV",
    ]
    assert normalize_validation_type("Regularizaci?n multiviaje transbordo") == ("regularizacion_multiviaje_transbordo")
    assert normalize_validation_type("Regularización multiviaje en salida") == ("regularizacion_multiviaje")


def test_filter_validation_rows_to_modeling_trips_applies_complete_scope() -> None:
    validation_types = [
        "Primera entrada",
        "Primera salida",
        "Entrada multiviaje",
        "Salida multiviaje",
        "Transbordo sencillo",
        "Regularizacion en salida",
        "Regularizacion sencilla",
        "Regularizacion multiviaje",
        "Transbordo multiviaje",
        "Regularizacion multiviaje transbordo",
        "Texto no reconocido",
    ]
    raw = pd.DataFrame(
        {
            "tipo_validacion": validation_types,
            "tipo_titulo": ["Monedero Metro Malaga"] * len(validation_types),
            "value": range(len(validation_types)),
        }
    )

    filtered = filter_validation_rows_to_modeling_trips(raw)

    assert filtered["tipo_validacion_normalizada"].tolist() == [
        "primera_entrada",
        "entrada_multiviaje",
        "transbordo_sencillo",
        "regularizacion_en_salida",
        "regularizacion_sencilla",
        "regularizacion_multiviaje",
        "transbordo_multiviaje",
        "regularizacion_multiviaje_transbordo",
    ]
    assert set(filtered["value"]) == {0, 2, 4, 5, 6, 7, 8, 9}


def test_filter_validation_rows_to_modeling_trips_applies_complete_title_scope() -> None:
    allowed_titles = [
        "Monedero Consorcio",
        "Monedero Metro Malaga",
        "Monedero Metro Malaga PVC",
        "Billete ocasional",
        "Monedero Consorcio para Familia Numerosa",
        "Monedero Consorcio FN",
        "Monedero EMV",
        "MásMetro",
        "Monedero ABT",
        "Título Promocional",
    ]
    excluded_titles = [
        "Monedero Descuentos Progresivos",
        "Contrata",
        "Pase Gratuito",
        "Titulo Visitas",
    ]
    raw = pd.DataFrame(
        {
            "tipo_validacion": ["Primera entrada"] * (len(allowed_titles) + len(excluded_titles)),
            "tipo_titulo": [*allowed_titles, *excluded_titles],
            "value": range(len(allowed_titles) + len(excluded_titles)),
        }
    )

    filtered = filter_validation_rows_to_modeling_trips(raw)

    assert filtered["tipo_titulo_limpio"].tolist() == allowed_titles
    assert set(filtered["value"]) == set(range(len(allowed_titles)))


def test_external_daily_features_extend_calendar_when_demand_is_newer() -> None:
    external = _build_external_daily_frame(["2026-01-01", "2026-01-02"])
    required_dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-03"]))

    extended = ensure_external_daily_feature_coverage(external, required_dates)
    generated = extended.loc[extended["date"] == pd.Timestamp("2026-01-03")].iloc[0]

    assert len(extended) == 3
    assert generated["year"] == 2026
    assert generated["month"] == 1
    assert generated["day"] == 3
    assert bool(generated["is_weekend"]) is True
    assert generated["run_id"] == "auto_calendar_extension_missing_external_context"


def test_safe_left_join_raises_when_right_side_is_not_unique() -> None:
    left = pd.DataFrame({"service_date": [pd.Timestamp("2026-01-01")], "linea": ["LINEA 1"]})
    right = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-01")],
            "value": [1, 2],
        }
    )

    with pytest.raises(ValueError, match="duplicated rows for key"):
        safe_left_join(
            left,
            right,
            left_name="left",
            right_name="right",
            left_keys=["service_date"],
            right_keys=["date"],
            required=True,
            right_unique=True,
        )


def test_build_network_changes_daily_context_aggregates_change_types() -> None:
    history = pd.DataFrame(
        {
            "change_type": [
                "equipment_first_seen",
                "equipment_first_seen",
                "line_station_first_seen",
            ],
            "effective_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "linea": ["LINEA 1", "LINEA 1", "LINEA 2"],
            "estacion": ["Perchel", "Perchel", "La Isla"],
            "cod_eq": ["PCH-001", "PCH-002", None],
            "notes": ["a", "b", "c"],
        }
    )

    context = build_network_changes_daily_context(history)

    perchel = context.loc[
        (context["service_date"] == pd.Timestamp("2026-01-01"))
        & (context["linea"] == "LINEA 1")
        & (context["estacion"] == "Perchel")
    ].iloc[0]
    assert perchel["network_equipment_first_seen_count"] == 2
    assert perchel["network_change_count"] == 2

    la_isla = context.loc[
        (context["service_date"] == pd.Timestamp("2026-01-02"))
        & (context["linea"] == "LINEA 2")
        & (context["estacion"] == "La Isla")
    ].iloc[0]
    assert la_isla["network_line_station_first_seen_count"] == 1


def test_prepare_modeling_base_dataset_joins_expected_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = _build_test_frames()
    settings = load_settings(PROJECT_ROOT)
    aggregated_target = pd.DataFrame(
        {
            "service_date": [
                pd.Timestamp("2026-01-01"),
                pd.Timestamp("2026-01-01"),
                pd.Timestamp("2026-01-02"),
            ],
            "linea": ["LINEA 1", "LINEA 1", "LINEA 2"],
            "estacion": ["Perchel", "Atarazanas", "La Isla"],
            "trip_count": [2, 1, 1],
            "first_trip_timestamp": pd.to_datetime(
                [
                    "2026-01-01 08:10:00",
                    "2026-01-01 09:00:00",
                    "2026-01-02 10:00:00",
                ]
            ).tz_localize("Europe/Madrid"),
            "last_trip_timestamp": pd.to_datetime(
                [
                    "2026-01-01 08:15:00",
                    "2026-01-01 09:00:00",
                    "2026-01-02 10:00:00",
                ]
            ).tz_localize("Europe/Madrid"),
            "raw_unique_equipment_count": [2, 1, 1],
            "raw_rows_with_estimated_time": [1, 0, 0],
            "raw_missing_money_fields_count": [0, 1, 1],
            "raw_missing_trip_fields_count": [0, 1, 0],
        }
    )

    def fake_load_validated_contract_table(
        _settings: dict[str, object],
        contract_name: str,
    ) -> pd.DataFrame:
        return frames[contract_name].copy()

    monkeypatch.setattr(
        modeling,
        "aggregate_trips_to_station_daily",
        lambda *args, **kwargs: aggregated_target.copy(),
    )
    monkeypatch.setattr(
        modeling,
        "load_validated_contract_table",
        fake_load_validated_contract_table,
    )

    bundle = prepare_modeling_base_dataset(settings, batch_size=2)
    model_base = bundle.model_base

    assert len(model_base) == 3
    assert model_base["trip_count"].sum() == 4
    assert "station_join_key" in model_base.columns
    assert "series_id" in model_base.columns
    assert "temp_mean_c" in model_base.columns
    assert "network_change_count" in model_base.columns
    assert "external_features_run_id" in model_base.columns
    assert model_base["series_id"].nunique() == 3

    perchel_row = model_base.loc[
        (model_base["service_date"] == pd.Timestamp("2026-01-01"))
        & (model_base["linea"] == "LINEA 1")
        & (model_base["estacion"] == "Perchel")
    ].iloc[0]
    assert perchel_row["series_id"] == "PCH1"
    assert perchel_row["station_join_key"] == "perchel"
    assert perchel_row["line_reference_path"] == "TCH -> ATZ"
    assert perchel_row["network_change_count"] == 2

    la_isla_row = model_base.loc[
        (model_base["service_date"] == pd.Timestamp("2026-01-02"))
        & (model_base["linea"] == "LINEA 2")
        & (model_base["estacion"] == "La Isla")
    ].iloc[0]
    assert la_isla_row["station_join_key"] == "la isla"
    assert la_isla_row["network_change_count"] == 0
