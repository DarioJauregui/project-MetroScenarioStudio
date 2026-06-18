from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.dataset as ds

from metro_demand_models.configuration import Settings
from metro_demand_models.data.contracts import (
    DatasetContract,
    load_dataset_contracts,
    load_join_contracts,
    load_service_day_policy,
    load_series_contract,
)
from metro_demand_models.data.io import read_table
from metro_demand_models.data.validation import (
    validate_dataset_contract,
    validate_non_null_columns,
    validate_unique_key,
)
from metro_demand_models.utils.stations import (
    build_station_series_label,
    infer_shared_station_abbreviations,
    normalize_station_abbrev,
)


SAFE_STATION_REFERENCE_COLUMNS = [
    "linea",
    "estacion",
    "station_join_key",
    "station_display_name",
    "station_abbrev",
    "network_order",
    "lat",
    "lon",
    "zone",
    "station_group",
    "is_interchange_candidate",
    "station_reference_label",
]

SAFE_LINE_REFERENCE_COLUMNS = [
    "linea",
    "line_reference_path",
]

CANONICAL_VALIDATION_TYPES = {
    "primera_entrada",
    "primera_salida",
    "entrada_multiviaje",
    "salida_multiviaje",
    "transbordo_sencillo",
    "regularizacion_en_salida",
    "regularizacion_sencilla",
    "regularizacion_multiviaje",
    "transbordo_multiviaje",
    "regularizacion_multiviaje_transbordo",
    "desconocida",
}

VALIDATION_TYPE_MARKERS_INCLUDED_IN_TRIPS = (
    "entrada",
    "regularizacion",
    "transbordo",
)

_VALIDATION_TYPE_LOOKUP = {
    "primera entrada": "primera_entrada",
    "primera salida": "primera_salida",
    "entrada multiviaje": "entrada_multiviaje",
    "salida multiviaje": "salida_multiviaje",
    "transbordo sencillo": "transbordo_sencillo",
    "regularizacion en salida": "regularizacion_en_salida",
    "regularizacion sencilla": "regularizacion_sencilla",
    "regularizacion sencilla transbordo": "regularizacion_sencilla",
    "regularizacion multiviaje": "regularizacion_multiviaje",
    "regularizacion multiviaje en salida": "regularizacion_multiviaje",
    "transbordo multiviaje": "transbordo_multiviaje",
    "regularizacion multiviaje transbordo": (
        "regularizacion_multiviaje_transbordo"
    ),
}

ALLOWED_TITLE_TYPES = (
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
)

EXCLUDED_TITLE_TYPES = (
    "Monedero Descuentos Progresivos",
    "Contrata",
    "Pase Gratuito",
    "Titulo Visitas",
)


@dataclass(frozen=True)
class ModelingDataBundle:
    station_daily_trips: pd.DataFrame
    external_daily_features: pd.DataFrame
    station_reference: pd.DataFrame
    line_reference: pd.DataFrame
    network_changes_daily: pd.DataFrame
    equipment_master: pd.DataFrame
    equipment_significant_master: pd.DataFrame
    auxiliary_station_config: pd.DataFrame
    model_base: pd.DataFrame


def build_service_date(
    series: pd.Series,
    *,
    boundary_hour: int = 0,
    boundary_minute: int = 0,
) -> pd.Series:
    """Build the service_date from the local event timestamp.

    In Phase 2A the default policy is the natural local calendar day
    (boundary at 00:00). The boundary remains configurable so a future
    operational day definition can be introduced without breaking the API.
    """

    timestamps = pd.to_datetime(series, errors="coerce")
    if boundary_hour or boundary_minute:
        timestamps = timestamps - pd.to_timedelta(
            (boundary_hour * 60) + boundary_minute,
            unit="m",
        )
    if getattr(timestamps.dt, "tz", None) is not None:
        timestamps = timestamps.dt.tz_localize(None)
    return timestamps.dt.normalize()


def load_validated_contract_table(
    settings: Settings,
    contract_name: str,
) -> pd.DataFrame:
    contracts = load_dataset_contracts(settings)
    contract = contracts[contract_name]
    dataframe = read_table(contract.resolve_path(settings))
    non_null_key_columns = tuple(
        column
        for column in contract.unique_key
        if column in contract.required_columns
    )

    validate_dataset_contract(
        dataframe,
        required_columns=contract.required_columns,
        unique_key=contract.unique_key,
        non_null_key_columns=non_null_key_columns,
        dataset_name=contract.name,
    )

    return dataframe


def normalize_text_for_matching(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()
    try:
        text = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        pass
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    text = text.lower()
    text = text.replace("regularizaci?n", "regularizacion")
    text = text.replace("m?smetro", "masmetro")
    text = text.replace("t?tulo", "titulo")
    text = text.replace("_", " ").replace("-", " ")
    return " ".join(text.split())


_TITLE_TYPE_LOOKUP = {
    normalize_text_for_matching(title_type): title_type
    for title_type in ALLOWED_TITLE_TYPES
}


def normalize_validation_type(value: object) -> str:
    normalized = normalize_text_for_matching(value)
    canonical = _VALIDATION_TYPE_LOOKUP.get(normalized, "desconocida")
    if canonical not in CANONICAL_VALIDATION_TYPES:
        raise ValueError(f"Unexpected canonical validation type '{canonical}'.")
    return canonical


def normalize_validation_type_series(series: pd.Series) -> pd.Series:
    raw_to_canonical = {
        value: normalize_validation_type(value)
        for value in series.dropna().unique()
    }
    return series.map(raw_to_canonical).fillna("desconocida")


def clean_title_type_series(series: pd.Series) -> pd.Series:
    raw_to_canonical = {
        value: _TITLE_TYPE_LOOKUP.get(normalize_text_for_matching(value), pd.NA)
        for value in series.dropna().unique()
    }
    return series.map(raw_to_canonical)


def filter_validation_rows_to_modeling_trips(
    dataframe: pd.DataFrame,
    *,
    validation_type_column: str = "tipo_validacion",
    title_type_column: str | None = None,
) -> pd.DataFrame:
    """Keep raw ticketing validation rows that represent modelable trips."""

    resolved_title_column = (
        title_type_column
        or (
            "tipo_titulo_limpio"
            if "tipo_titulo_limpio" in dataframe.columns
            else "tipo_titulo"
        )
    )
    missing_columns = [
        column
        for column in [validation_type_column, resolved_title_column]
        if column not in dataframe.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise KeyError(f"Missing required validation filtering columns: {missing}.")

    filtered = dataframe.copy()
    filtered["tipo_validacion_normalizada"] = normalize_validation_type_series(
        filtered[validation_type_column]
    )
    filtered["tipo_titulo_limpio"] = clean_title_type_series(
        filtered[resolved_title_column]
    )

    validation_scope = filtered["tipo_validacion_normalizada"].str.contains(
        "|".join(VALIDATION_TYPE_MARKERS_INCLUDED_IN_TRIPS),
        regex=True,
        na=False,
    )
    title_scope = filtered["tipo_titulo_limpio"].notna()
    return filtered.loc[validation_scope & title_scope].reset_index(drop=True)


def ensure_external_daily_feature_coverage(
    external_daily_features: pd.DataFrame,
    required_dates: pd.Series,
) -> pd.DataFrame:
    """Extend deterministic daily context when demand is newer than external files.

    Calendar columns can be derived from the date itself. Weather and duplicated
    event signals remain unavailable in the generated rows; downstream strict
    baselines do not use them, and scenario models can still treat them as missing.
    """

    frame = external_daily_features.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    required = pd.to_datetime(required_dates, errors="coerce").dropna().dt.normalize()
    missing_dates = sorted(set(required).difference(set(frame["date"].dropna())))
    if not missing_dates:
        return frame.sort_values("date").reset_index(drop=True)

    generated = _build_external_calendar_extension_rows(
        pd.DatetimeIndex(missing_dates),
        columns=list(frame.columns),
    )
    combined = pd.concat([frame, generated], ignore_index=True)
    validate_unique_key(
        combined,
        ["date"],
        dataset_name="external_daily_features_with_calendar_extension",
    )
    return combined.sort_values("date").reset_index(drop=True)


def _build_external_calendar_extension_rows(
    dates: pd.DatetimeIndex,
    *,
    columns: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date_value in dates:
        current_date = pd.Timestamp(date_value).normalize()
        iso_week = current_date.isocalendar()
        row: dict[str, Any] = {column: pd.NA for column in columns}
        row.update(
            {
                "date": current_date,
                "year": int(current_date.year),
                "month": int(current_date.month),
                "day": int(current_date.day),
                "quarter": int(current_date.quarter),
                "week_of_year": int(iso_week.week),
                "day_of_year": int(current_date.day_of_year),
                "day_of_week": int(current_date.dayofweek + 1),
                "day_of_week_name": current_date.day_name(),
                "is_weekend": bool(current_date.dayofweek >= 5),
                "is_holiday": False,
                "holiday_name": "",
                "holiday_scope": "",
                "is_holiday_mmo": False,
                "is_preholiday": False,
                "is_postholiday": False,
                "days_to_next_holiday": float("nan"),
                "days_since_prev_holiday": float("nan"),
                "is_bridge_candidate": False,
                "is_month_start": bool(current_date.is_month_start),
                "is_month_end": bool(current_date.is_month_end),
                "temp_min_c": float("nan"),
                "temp_max_c": float("nan"),
                "temp_mean_c": float("nan"),
                "precip_mm": float("nan"),
                "rain_hours": float("nan"),
                "wind_max_kmh": float("nan"),
                "wind_mean_kmh": float("nan"),
                "humidity_mean_pct": float("nan"),
                "pressure_mean_hpa": float("nan"),
                "weather_code": pd.NA,
                "weather_source": "unavailable",
                "weather_summary": "unavailable",
                "is_rainy_day": False,
                "is_heavy_rain_day": False,
                "is_hot_day": False,
                "is_cold_day": False,
                "is_bad_weather_day": False,
                "events_total_count": 0,
                "events_high_impact_count": 0,
                "events_estimated_attendance_sum": 0.0,
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
                "run_id": "auto_calendar_extension_missing_external_context",
                "year_month": current_date.strftime("%Y-%m"),
                "year_week": f"{current_date.year}-{int(iso_week.week):02d}",
            }
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def build_station_reference(stations_master: pd.DataFrame) -> pd.DataFrame:
    reference = stations_master[SAFE_STATION_REFERENCE_COLUMNS].copy()
    reference["station_abbrev"] = reference["station_abbrev"].map(
        normalize_station_abbrev
    )
    validate_unique_key(
        reference,
        ["linea", "estacion"],
        dataset_name="stations_master_reference",
    )
    return reference.sort_values(["linea", "network_order"]).reset_index(drop=True)


def build_line_reference(lines_master: pd.DataFrame) -> pd.DataFrame:
    reference = lines_master[SAFE_LINE_REFERENCE_COLUMNS].copy()
    validate_unique_key(reference, ["linea"], dataset_name="lines_master_reference")
    return reference.sort_values(["linea"]).reset_index(drop=True)


def build_network_changes_daily_context(
    network_changes_history: pd.DataFrame,
    *,
    boundary_hour: int = 0,
    boundary_minute: int = 0,
) -> pd.DataFrame:
    working = network_changes_history.copy()
    working["service_date"] = build_service_date(
        working["effective_date"],
        boundary_hour=boundary_hour,
        boundary_minute=boundary_minute,
    )
    working["change_count"] = 1

    pivot = (
        working.pivot_table(
            index=["service_date", "linea", "estacion"],
            columns="change_type",
            values="change_count",
            aggfunc="sum",
            fill_value=0,
        )
        .rename_axis(columns=None)
        .reset_index()
    )

    rename_map = {
        "equipment_first_seen": "network_equipment_first_seen_count",
        "equipment_last_seen_observed": "network_equipment_last_seen_observed_count",
        "line_station_first_seen": "network_line_station_first_seen_count",
        "line_station_last_seen_observed": (
            "network_line_station_last_seen_observed_count"
        ),
    }
    pivot = pivot.rename(columns=rename_map)

    for column in rename_map.values():
        if column not in pivot.columns:
            pivot[column] = 0

    count_columns = list(rename_map.values())
    pivot["network_change_count"] = pivot[count_columns].sum(axis=1)

    validate_unique_key(
        pivot,
        ["service_date", "linea", "estacion"],
        dataset_name="network_changes_daily",
    )

    return pivot.sort_values(["service_date", "linea", "estacion"]).reset_index(
        drop=True
    )


def aggregate_trips_to_station_daily(
    validation_rows_path: Path | str,
    *,
    batch_size: int = 250_000,
    service_day_boundary_hour: int = 0,
    service_day_boundary_minute: int = 0,
) -> pd.DataFrame:
    """Aggregate filtered trip rows incrementally to a daily line-station base.

    The implementation intentionally avoids loading the ~190M-row raw table into
    memory. It scans the raw ticketing validation Parquet file in batches, applies
    the trip-scope filter first, and keeps only the compact aggregation state
    needed for the final daily dataset.
    """

    dataset = ds.dataset(validation_rows_path, format="parquet")
    dataset_columns = set(dataset.schema.names)
    title_type_column = (
        "tipo_titulo_limpio"
        if "tipo_titulo_limpio" in dataset_columns
        else "tipo_titulo"
    )
    scanner = dataset.scanner(
        columns=[
            "fecha_validacion",
            "linea",
            "estacion",
            "cod_eq",
            "tipo_validacion",
            title_type_column,
            "dinero_deducido",
            "saldo_restante",
            "viajes_deducidos",
            "fecha_validacion_hora_estimada",
        ],
        batch_size=batch_size,
    )

    aggregate_state: dict[
        tuple[pd.Timestamp, str, str], dict[str, Any]
    ] = {}
    equipment_seen: dict[tuple[pd.Timestamp, str, str], set[str]] = defaultdict(set)

    for batch in scanner.to_batches():
        dataframe = batch.to_pandas()
        dataframe = filter_validation_rows_to_modeling_trips(
            dataframe,
            title_type_column=title_type_column,
        )
        if dataframe.empty:
            continue
        dataframe["fecha_validacion"] = pd.to_datetime(
            dataframe["fecha_validacion"],
            errors="coerce",
        )
        dataframe["service_date"] = build_service_date(
            dataframe["fecha_validacion"],
            boundary_hour=service_day_boundary_hour,
            boundary_minute=service_day_boundary_minute,
        )
        dataframe["raw_rows_with_estimated_time"] = (
            dataframe["fecha_validacion_hora_estimada"].fillna(False).astype(int)
        )
        dataframe["raw_missing_money_fields_count"] = (
            dataframe["dinero_deducido"].isna() | dataframe["saldo_restante"].isna()
        ).astype(int)
        dataframe["raw_missing_trip_fields_count"] = dataframe[
            "viajes_deducidos"
        ].isna().astype(int)

        working = dataframe.dropna(
            subset=["service_date", "fecha_validacion", "linea", "estacion"]
        )
        grouped = working.groupby(
            ["service_date", "linea", "estacion"],
            dropna=False,
        ).agg(
            trip_count=("fecha_validacion", "size"),
            first_trip_timestamp=("fecha_validacion", "min"),
            last_trip_timestamp=("fecha_validacion", "max"),
            raw_rows_with_estimated_time=("raw_rows_with_estimated_time", "sum"),
            raw_missing_money_fields_count=(
                "raw_missing_money_fields_count",
                "sum",
            ),
            raw_missing_trip_fields_count=(
                "raw_missing_trip_fields_count",
                "sum",
            ),
        )

        for key, row in grouped.iterrows():
            state = aggregate_state.setdefault(
                key,
                {
                    "trip_count": 0,
                    "first_trip_timestamp": row["first_trip_timestamp"],
                    "last_trip_timestamp": row["last_trip_timestamp"],
                    "raw_rows_with_estimated_time": 0,
                    "raw_missing_money_fields_count": 0,
                    "raw_missing_trip_fields_count": 0,
                },
            )
            state["trip_count"] += int(row["trip_count"])
            state["raw_rows_with_estimated_time"] += int(
                row["raw_rows_with_estimated_time"]
            )
            state["raw_missing_money_fields_count"] += int(
                row["raw_missing_money_fields_count"]
            )
            state["raw_missing_trip_fields_count"] += int(
                row["raw_missing_trip_fields_count"]
            )
            if row["first_trip_timestamp"] < state["first_trip_timestamp"]:
                state["first_trip_timestamp"] = row["first_trip_timestamp"]
            if row["last_trip_timestamp"] > state["last_trip_timestamp"]:
                state["last_trip_timestamp"] = row["last_trip_timestamp"]

        unique_equipment = working[
            ["service_date", "linea", "estacion", "cod_eq"]
        ].dropna(subset=["cod_eq"])
        unique_equipment = unique_equipment.drop_duplicates()
        for row in unique_equipment.itertuples(index=False):
            key = (row.service_date, row.linea, row.estacion)
            equipment_seen[key].add(str(row.cod_eq))

    records: list[dict[str, Any]] = []
    for key, state in aggregate_state.items():
        service_date, linea, estacion = key
        records.append(
            {
                "service_date": service_date,
                "linea": linea,
                "estacion": estacion,
                "trip_count": state["trip_count"],
                "first_trip_timestamp": state["first_trip_timestamp"],
                "last_trip_timestamp": state["last_trip_timestamp"],
                "raw_unique_equipment_count": len(equipment_seen.get(key, set())),
                "raw_rows_with_estimated_time": state[
                    "raw_rows_with_estimated_time"
                ],
                "raw_missing_money_fields_count": state[
                    "raw_missing_money_fields_count"
                ],
                "raw_missing_trip_fields_count": state[
                    "raw_missing_trip_fields_count"
                ],
            }
        )

    result = pd.DataFrame.from_records(records)
    validate_dataset_contract(
        result,
        required_columns=[
            "service_date",
            "linea",
            "estacion",
            "trip_count",
        ],
        unique_key=["service_date", "linea", "estacion"],
        non_null_key_columns=["service_date", "linea", "estacion"],
        dataset_name="station_daily_trips",
    )
    return result.sort_values(["service_date", "linea", "estacion"]).reset_index(
        drop=True
    )


def _apply_zero_fill(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    for column in columns:
        if column in dataframe.columns:
            dataframe[column] = dataframe[column].fillna(0).astype(int)
    return dataframe


def safe_left_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_name: str,
    right_name: str,
    left_keys: list[str],
    right_keys: list[str],
    required: bool,
    right_unique: bool,
) -> pd.DataFrame:
    validate_non_null_columns(left, left_keys, dataset_name=left_name)
    if right_unique:
        validate_unique_key(right, right_keys, dataset_name=right_name)

    merged = left.merge(
        right,
        how="left",
        left_on=left_keys,
        right_on=right_keys,
        validate="m:1" if right_unique else "m:m",
        indicator=True,
        suffixes=("", f"_{right_name}"),
    )
    if len(merged) != len(left):
        raise ValueError(
            f"Join between '{left_name}' and '{right_name}' changed the row count "
            f"from {len(left)} to {len(merged)}."
        )

    if required:
        missing_rows = merged[merged["_merge"] != "both"]
        if not missing_rows.empty:
            preview = missing_rows[left_keys].drop_duplicates().head(5).to_dict(
                orient="records"
            )
            raise ValueError(
                f"Required join '{left_name}' -> '{right_name}' has missing matches. "
                f"Examples: {preview}."
            )

    merged = merged.drop(columns=["_merge"])

    for key in right_keys:
        if key not in left.columns and key in merged.columns:
            merged = merged.drop(columns=[key])

    return merged


def prepare_modeling_base_dataset(
    settings: Settings,
    *,
    batch_size: int | None = None,
    include_optional_context: bool = True,
) -> ModelingDataBundle:
    dataset_contracts = load_dataset_contracts(settings)
    join_contracts = load_join_contracts(settings)
    service_day_policy = load_service_day_policy(settings)
    series_contract = load_series_contract(settings)
    configured_batch_size = int(
        settings["modeling"]["execution"]["trip_scanner_batch_size"]
    )

    validations_contract = dataset_contracts["validations"]
    station_daily_trips = aggregate_trips_to_station_daily(
        validations_contract.resolve_path(settings),
        batch_size=batch_size or configured_batch_size,
        service_day_boundary_hour=service_day_policy.boundary_hour,
        service_day_boundary_minute=service_day_policy.boundary_minute,
    )

    external_daily_features = load_validated_contract_table(
        settings,
        "external_daily_features",
    )
    external_daily_features["date"] = build_service_date(
        external_daily_features["date"],
        boundary_hour=service_day_policy.boundary_hour,
        boundary_minute=service_day_policy.boundary_minute,
    )
    external_daily_features = ensure_external_daily_feature_coverage(
        external_daily_features,
        station_daily_trips["service_date"],
    )

    stations_master = load_validated_contract_table(settings, "stations_master")
    lines_master = load_validated_contract_table(settings, "lines_master")
    equipment_master = load_validated_contract_table(settings, "equipment_master")
    equipment_significant_master = load_validated_contract_table(
        settings,
        "equipment_significant_master",
    )
    network_changes_history = load_validated_contract_table(
        settings,
        "network_changes_history",
    )
    auxiliary_station_config = load_validated_contract_table(settings, "metro_stations")

    station_reference = build_station_reference(stations_master)
    line_reference = build_line_reference(lines_master)
    network_changes_daily = build_network_changes_daily_context(
        network_changes_history,
        boundary_hour=service_day_policy.boundary_hour,
        boundary_minute=service_day_policy.boundary_minute,
    )

    external_join = join_contracts["trips_to_external_daily_features"]
    model_base = safe_left_join(
        station_daily_trips,
        external_daily_features,
        left_name=external_join.left_dataset,
        right_name=external_join.right_dataset,
        left_keys=list(external_join.left_keys),
        right_keys=list(external_join.right_keys),
        required=external_join.required,
        right_unique=external_join.right_unique,
    )
    if "run_id" in model_base.columns:
        model_base = model_base.rename(columns={"run_id": "external_features_run_id"})

    station_join = join_contracts["station_daily_to_stations_master"]
    model_base = safe_left_join(
        model_base,
        station_reference,
        left_name=station_join.left_dataset,
        right_name=station_join.right_dataset,
        left_keys=list(station_join.left_keys),
        right_keys=list(station_join.right_keys),
        required=station_join.required,
        right_unique=station_join.right_unique,
    )

    line_join = join_contracts["station_daily_to_lines_master"]
    model_base = safe_left_join(
        model_base,
        line_reference,
        left_name=line_join.left_dataset,
        right_name=line_join.right_dataset,
        left_keys=list(line_join.left_keys),
        right_keys=list(line_join.right_keys),
        required=False,
        right_unique=line_join.right_unique,
    )

    if include_optional_context:
        network_join = join_contracts["station_daily_to_network_changes"]
        model_base = safe_left_join(
            model_base,
            network_changes_daily,
            left_name=network_join.left_dataset,
            right_name=network_join.right_dataset,
            left_keys=list(network_join.left_keys),
            right_keys=list(network_join.right_keys),
            required=False,
            right_unique=network_join.right_unique,
        )
        model_base = _apply_zero_fill(
            model_base,
            [
                "network_change_count",
                "network_equipment_first_seen_count",
                "network_equipment_last_seen_observed_count",
                "network_line_station_first_seen_count",
                "network_line_station_last_seen_observed_count",
            ],
        )

    shared_station_abbreviations = infer_shared_station_abbreviations(station_reference)
    model_base[series_contract.series_id_column] = model_base.apply(
        lambda row: build_station_series_label(
            linea=row["linea"],
            station_abbrev=row["station_abbrev"],
            shared_station_abbreviations=shared_station_abbreviations,
        ),
        axis=1,
    )

    validate_dataset_contract(
        model_base,
        required_columns=[
            "service_date",
            series_contract.series_id_column,
            "linea",
            "estacion",
            "station_join_key",
            "station_reference_label",
            "trip_count",
        ],
        unique_key=["service_date", series_contract.series_id_column],
        non_null_key_columns=[
            "service_date",
            series_contract.series_id_column,
            "linea",
            "estacion",
            "station_join_key",
        ],
        dataset_name="phase_2a_station_daily_model_base",
    )

    model_base = model_base.sort_values(
        ["service_date", "linea", "network_order", "estacion"]
    ).reset_index(drop=True)

    return ModelingDataBundle(
        station_daily_trips=station_daily_trips,
        external_daily_features=external_daily_features,
        station_reference=station_reference,
        line_reference=line_reference,
        network_changes_daily=network_changes_daily,
        equipment_master=equipment_master,
        equipment_significant_master=equipment_significant_master,
        auxiliary_station_config=auxiliary_station_config,
        model_base=model_base,
    )


def summarize_dataset_contract(
    settings: Settings,
    contract: DatasetContract,
) -> dict[str, Any]:
    dataframe = load_validated_contract_table(settings, contract.name)
    return {
        "dataset_name": contract.name,
        "path": str(contract.resolve_path(settings)),
        "rows": int(len(dataframe)),
        "columns": list(dataframe.columns),
        "unique_key": list(contract.unique_key),
    }
