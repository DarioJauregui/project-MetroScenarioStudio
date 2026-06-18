from __future__ import annotations

from dataclasses import asdict, dataclass
import re

import pandas as pd

from metro_demand_models.data.contracts import WorkbookSourceContract
from metro_demand_models.data.inspection import DatasetInspection, inspect_dataframe
from metro_demand_models.data.operations.common import (
    build_station_group_reference,
    canonicalize_station_code,
    normalize_match_label,
)


@dataclass(frozen=True)
class IncidentsInspection:
    dataset: DatasetInspection
    rows_with_station_mapping: int
    rows_with_line_scope: int
    rows_with_crossing_scope: int
    rows_with_depot_scope: int
    rows_with_network_scope: int
    rows_with_rolling_stock_scope: int
    rows_with_overnight_end: int

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset"] = self.dataset.to_dict()
        return payload


def inspect_incidents_history(
    dataframe: pd.DataFrame,
    *,
    dataset_path: str,
    contract: WorkbookSourceContract,
    stations_master: pd.DataFrame,
    alias_map: dict[str, str],
    line_values: dict[str, str],
    depot_keywords: tuple[str, ...],
    crossing_keywords: tuple[str, ...],
    network_keywords: tuple[str, ...],
) -> IncidentsInspection:
    inspection = inspect_dataframe(
        dataframe,
        dataset_name=contract.name,
        dataset_path=dataset_path,
        duplicate_key=("id",),
        date_columns=("fecha_origen_inc",),
    )
    normalized = normalize_incidents_history(
        dataframe,
        stations_master=stations_master,
        alias_map=alias_map,
        line_values=line_values,
        depot_keywords=depot_keywords,
        crossing_keywords=crossing_keywords,
        network_keywords=network_keywords,
    )
    return IncidentsInspection(
        dataset=inspection,
        rows_with_station_mapping=int(normalized["mapped_station_abbrev"].notna().sum()),
        rows_with_line_scope=int(normalized["impact_scope"].eq("line").sum()),
        rows_with_crossing_scope=int(normalized["impact_scope"].eq("crossing").sum()),
        rows_with_depot_scope=int(normalized["impact_scope"].eq("depot").sum()),
        rows_with_network_scope=int(normalized["impact_scope"].eq("network").sum()),
        rows_with_rolling_stock_scope=int(
            normalized["impact_scope"].eq("rolling_stock_or_asset").sum()
        ),
        rows_with_overnight_end=int(normalized["end_ts_correction_applied"].sum()),
    )


def normalize_incidents_history(
    dataframe: pd.DataFrame,
    *,
    stations_master: pd.DataFrame,
    alias_map: dict[str, str],
    line_values: dict[str, str],
    depot_keywords: tuple[str, ...],
    crossing_keywords: tuple[str, ...],
    network_keywords: tuple[str, ...],
) -> pd.DataFrame:
    station_reference = build_station_group_reference(stations_master)
    line_lookup = _build_station_line_lookup(stations_master)

    normalized = dataframe.copy().sort_values("id").reset_index(drop=True)
    normalized["service_date"] = pd.to_datetime(normalized["fecha_origen_inc"]).dt.date
    normalized["incident_start_ts"] = _combine_date_time(
        normalized["fecha_origen_inc"],
        normalized["hora_inicio"],
    )
    raw_end_ts = _combine_date_time(
        normalized["fecha_origen_inc"],
        normalized["hora_fin"],
    )
    normalized["incident_end_ts"] = raw_end_ts.where(
        raw_end_ts.isna()
        | normalized["incident_start_ts"].isna()
        | (raw_end_ts >= normalized["incident_start_ts"]),
        raw_end_ts + pd.Timedelta(days=1),
    )
    normalized["end_ts_correction_applied"] = (
        raw_end_ts.notna()
        & normalized["incident_start_ts"].notna()
        & (raw_end_ts < normalized["incident_start_ts"])
    )
    normalized["incident_duration_minutes"] = (
        (
            normalized["incident_end_ts"] - normalized["incident_start_ts"]
        ).dt.total_seconds()
        / 60.0
    ).round(2)

    normalized["delay_duration_text_raw"] = normalized["tiempo_de_retraso_en_minutos"]
    normalized["delay_seconds"] = normalized["delay_duration_text_raw"].map(
        _parse_delay_seconds
    )
    normalized["delay_minutes"] = (
        normalized["delay_seconds"] / 60.0
    ).round(2)

    normalized["location_raw"] = normalized["localizacion"]
    normalized["location_key"] = normalized["location_raw"].map(normalize_match_label)
    station_prefix = normalized["location_raw"].astype("string").str.extract(
        r"^([A-Z]{3})\s*-",
        expand=False,
    )
    normalized["station_prefix_raw"] = station_prefix

    mapping_rows = normalized.apply(
        lambda row: _map_incident_location(
            row,
            station_reference=station_reference,
            line_lookup=line_lookup,
            alias_map=alias_map,
            line_values=line_values,
            depot_keywords=depot_keywords,
            crossing_keywords=crossing_keywords,
            network_keywords=network_keywords,
        ),
        axis=1,
        result_type="expand",
    )
    normalized = pd.concat([normalized, mapping_rows], axis=1)

    normalized["service_affectation"] = normalized["afeccion_al_servicio"]
    normalized["description"] = normalized["descripcion"]
    normalized["type_agent"] = normalized["tipo_agente"]
    normalized["incident_type"] = normalized["tipo_incidencia"]
    normalized["related_incidents"] = normalized["incidencias_asociadas"]
    normalized["group_name"] = normalized["grupo"]
    normalized["subgroup_name"] = normalized["subgrupo"]
    normalized["family_name"] = normalized["familia"]
    normalized["incident_code"] = normalized["codigo"]
    normalized["sub_location_raw"] = normalized["sublocalizacion"]
    normalized["location_type"] = normalized["tipo_localizacion"]
    normalized["system_name"] = normalized["sistema"]
    normalized["subsystem_name"] = normalized["subsistema"]
    normalized["source_row_number"] = normalized.index + 2

    return normalized[
        [
            "id",
            "service_date",
            "incident_start_ts",
            "incident_end_ts",
            "end_ts_correction_applied",
            "incident_duration_minutes",
            "delay_duration_text_raw",
            "delay_seconds",
            "delay_minutes",
            "location_raw",
            "location_key",
            "station_prefix_raw",
            "impact_scope",
            "mapped_linea",
            "mapped_station_abbrev",
            "mapped_station_join_key",
            "mapped_station_display_name",
            "mapping_confidence",
            "mapping_notes",
            "type_agent",
            "incident_type",
            "related_incidents",
            "group_name",
            "subgroup_name",
            "family_name",
            "incident_code",
            "sub_location_raw",
            "location_type",
            "description",
            "service_affectation",
            "system_name",
            "subsystem_name",
            "source_row_number",
        ]
    ].rename(columns={"id": "incident_id"})


def build_incidents_daily(normalized_incidents: pd.DataFrame) -> pd.DataFrame:
    daily = normalized_incidents.copy()
    affectation_key = daily["service_affectation"].map(normalize_match_label)
    daily["delay_incident_count"] = affectation_key.eq("retrasos").astype(int)
    daily["partial_service_incident_count"] = affectation_key.eq(
        "servicio parcial"
    ).astype(int)
    daily["line_stop_incident_count"] = affectation_key.eq("paro de la linea").astype(int)
    daily["single_track_incident_count"] = affectation_key.eq(
        "via unica temporal"
    ).astype(int)

    aggregated = (
        daily.groupby(
            [
                "service_date",
                "impact_scope",
                "mapped_linea",
                "mapped_station_abbrev",
                "mapped_station_join_key",
                "mapped_station_display_name",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            incident_count=("incident_id", "count"),
            delay_minutes_sum=("delay_minutes", "sum"),
            delay_minutes_max=("delay_minutes", "max"),
            incident_duration_minutes_sum=("incident_duration_minutes", "sum"),
            incident_duration_minutes_max=("incident_duration_minutes", "max"),
            delay_incident_count=("delay_incident_count", "sum"),
            partial_service_incident_count=("partial_service_incident_count", "sum"),
            line_stop_incident_count=("line_stop_incident_count", "sum"),
            single_track_incident_count=("single_track_incident_count", "sum"),
        )
        .sort_values(
            [
                "service_date",
                "impact_scope",
                "mapped_linea",
                "mapped_station_abbrev",
            ]
        )
    )
    return aggregated


def build_incidents_mapping_report(normalized_incidents: pd.DataFrame) -> pd.DataFrame:
    return (
        normalized_incidents.groupby(
            [
                "location_raw",
                "impact_scope",
                "station_prefix_raw",
                "mapped_station_abbrev",
                "mapped_linea",
                "mapping_confidence",
                "mapping_notes",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            incident_count=("incident_id", "count"),
            delay_minutes_sum=("delay_minutes", "sum"),
            latest_service_date=("service_date", "max"),
        )
        .sort_values(["incident_count", "location_raw"], ascending=[False, True])
    )


def _combine_date_time(date_series: pd.Series, time_series: pd.Series) -> pd.Series:
    date_part = pd.to_datetime(date_series, errors="coerce").dt.strftime("%Y-%m-%d")
    time_part = time_series.astype("string").str.strip()
    return pd.to_datetime(date_part + " " + time_part, errors="coerce")


def _parse_delay_seconds(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None

    cleaned = str(value).strip()
    if not cleaned:
        return None

    parts = cleaned.split(":")
    if len(parts) != 2:
        return None

    minutes = float(parts[0])
    seconds = float(parts[1])
    return (minutes * 60.0) + seconds


def _build_station_line_lookup(stations_master: pd.DataFrame) -> dict[str, tuple[str | None, int]]:
    summary = (
        stations_master.groupby("station_abbrev")
        .agg(primary_linea=("linea", "first"), line_count=("linea", "nunique"))
        .to_dict(orient="index")
    )
    return {
        code: (values["primary_linea"], int(values["line_count"]))
        for code, values in summary.items()
    }


def _map_incident_location(
    row: pd.Series,
    *,
    station_reference: pd.DataFrame,
    line_lookup: dict[str, tuple[str | None, int]],
    alias_map: dict[str, str],
    line_values: dict[str, str],
    depot_keywords: tuple[str, ...],
    crossing_keywords: tuple[str, ...],
    network_keywords: tuple[str, ...],
) -> dict[str, object]:
    location_raw = row["localizacion"]
    location_key = normalize_match_label(location_raw)
    station_prefix = row["station_prefix_raw"]
    canonical_station_code = None
    alias_kind = "missing"
    if station_prefix is not None and pd.notna(station_prefix):
        canonical_station_code, alias_kind = canonicalize_station_code(
            station_prefix,
            alias_map=alias_map,
        )

    station_match = (
        station_reference[station_reference["station_abbrev"] == canonical_station_code]
        if canonical_station_code is not None
        else pd.DataFrame()
    )
    if not station_match.empty:
        station_row = station_match.iloc[0]
        primary_linea, line_count = line_lookup.get(canonical_station_code, (None, 0))
        if line_count == 1:
            mapped_linea = primary_linea
            confidence_suffix = "unique_line"
            notes = None
        else:
            mapped_linea = pd.NA
            confidence_suffix = "shared_station"
            notes = "station_shared_between_lines"

        return {
            "impact_scope": "station",
            "mapped_linea": mapped_linea,
            "mapped_station_abbrev": canonical_station_code,
            "mapped_station_join_key": station_row["station_join_key"],
            "mapped_station_display_name": station_row["station_display_name"],
            "mapping_confidence": (
                f"station_prefix_{'alias' if alias_kind == 'alias' else 'exact'}_{confidence_suffix}"
            ),
            "mapping_notes": notes,
        }

    if location_key in line_values:
        return {
            "impact_scope": "line",
            "mapped_linea": line_values[location_key],
            "mapped_station_abbrev": pd.NA,
            "mapped_station_join_key": pd.NA,
            "mapped_station_display_name": pd.NA,
            "mapping_confidence": "line_exact",
            "mapping_notes": None,
        }

    if _contains_any_keyword(location_key, crossing_keywords):
        return _scope_only_mapping("crossing")

    if _contains_any_keyword(location_key, depot_keywords):
        return _scope_only_mapping("depot")

    if _contains_any_keyword(location_key, network_keywords):
        return _scope_only_mapping("network")

    if bool(re.fullmatch(r"\d+", str(location_raw).strip())):
        return _scope_only_mapping("rolling_stock_or_asset")

    return _scope_only_mapping("unknown")


def _contains_any_keyword(value: str, keywords: tuple[str, ...]) -> bool:
    normalized_keywords = {normalize_match_label(keyword) for keyword in keywords}
    return any(keyword and keyword in value for keyword in normalized_keywords)


def _scope_only_mapping(scope: str) -> dict[str, object]:
    return {
        "impact_scope": scope,
        "mapped_linea": pd.NA,
        "mapped_station_abbrev": pd.NA,
        "mapped_station_join_key": pd.NA,
        "mapped_station_display_name": pd.NA,
        "mapping_confidence": f"{scope}_scope",
        "mapping_notes": None,
    }
