from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from metro_demand_models.data.contracts import WorkbookSourceContract
from metro_demand_models.data.inspection import DatasetInspection, inspect_dataframe
from metro_demand_models.data.operations.common import (
    build_station_group_reference,
    canonicalize_station_code,
    expand_date_span,
    normalize_match_label,
    parse_attendance_value,
    serialize_list,
)


HIGH_IMPACT_ATTENDANCE_THRESHOLD = 10_000


@dataclass(frozen=True)
class EventsInspection:
    events_dataset: DatasetInspection
    locations_dataset: DatasetInspection
    unique_event_locations: int
    unique_mapping_locations: int
    event_rows_with_exact_mapping: int
    event_rows_with_normalized_mapping: int
    event_rows_with_negative_duration: int
    mapping_rows_with_multiple_station_codes: int
    mapping_rows_with_unknown_codes: int

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["events_dataset"] = self.events_dataset.to_dict()
        payload["locations_dataset"] = self.locations_dataset.to_dict()
        return payload


def inspect_event_sources(
    events_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    *,
    dataset_path: str,
    events_contract: WorkbookSourceContract,
    locations_contract: WorkbookSourceContract,
    alias_map: dict[str, str],
    non_station_codes: set[str],
    stations_master: pd.DataFrame,
) -> EventsInspection:
    events_dataset = inspect_dataframe(
        events_df,
        dataset_name=events_contract.name,
        dataset_path=dataset_path,
        duplicate_key=("id",),
        date_columns=("hora_inicio", "hora_fin"),
    )
    locations_dataset = inspect_dataframe(
        locations_df,
        dataset_name=locations_contract.name,
        dataset_path=dataset_path,
        duplicate_key=("ubicaciones",),
    )
    normalized_events = normalize_events_master(events_df)
    location_mapping = build_event_location_mapping(
        locations_df,
        stations_master=stations_master,
        alias_map=alias_map,
        non_station_codes=non_station_codes,
    )
    unique_location_mapping = location_mapping[
        ["location_raw", "station_mapping_count", "unknown_station_codes_present"]
    ].drop_duplicates()
    exact_keys = set(
        location_mapping["location_raw"].dropna().astype(str).str.strip().tolist()
    )
    normalized_keys = set(location_mapping["location_key"].dropna().tolist())
    return EventsInspection(
        events_dataset=events_dataset,
        locations_dataset=locations_dataset,
        unique_event_locations=int(normalized_events["location_raw"].nunique(dropna=True)),
        unique_mapping_locations=int(location_mapping["location_raw"].nunique(dropna=True)),
        event_rows_with_exact_mapping=int(
            normalized_events["location_raw"].astype(str).str.strip().isin(exact_keys).sum()
        ),
        event_rows_with_normalized_mapping=int(
            normalized_events["location_key"].isin(normalized_keys).sum()
        ),
        event_rows_with_negative_duration=int(
            normalized_events["end_ts_correction_applied"].sum()
        ),
        mapping_rows_with_multiple_station_codes=int(
            (unique_location_mapping["station_mapping_count"] > 1).sum()
        ),
        mapping_rows_with_unknown_codes=int(
            unique_location_mapping["unknown_station_codes_present"].notna().sum()
        ),
    )


def normalize_events_master(events_df: pd.DataFrame) -> pd.DataFrame:
    normalized = events_df.copy().sort_values("id").reset_index(drop=True)
    for optional_column in ("tipo_de_elemento", "ruta_de_acceso"):
        if optional_column not in normalized.columns:
            normalized[optional_column] = pd.NA
    normalized["start_ts"] = pd.to_datetime(normalized["hora_inicio"], errors="coerce")
    normalized["end_ts_raw"] = pd.to_datetime(normalized["hora_fin"], errors="coerce")
    normalized["end_ts"] = normalized["end_ts_raw"].where(
        normalized["end_ts_raw"].isna()
        | normalized["start_ts"].isna()
        | (normalized["end_ts_raw"] >= normalized["start_ts"]),
        normalized["end_ts_raw"] + pd.Timedelta(days=1),
    )
    normalized["end_ts_correction_applied"] = (
        normalized["end_ts_raw"].notna()
        & normalized["start_ts"].notna()
        & (normalized["end_ts_raw"] < normalized["start_ts"])
    )
    normalized["duration_minutes"] = (
        (normalized["end_ts"] - normalized["start_ts"]).dt.total_seconds() / 60.0
    ).round()
    normalized["location_raw"] = normalized["ubicacion"]
    normalized["location_key"] = normalized["location_raw"].map(normalize_match_label)
    normalized["attendance_raw"] = normalized["aforo"]
    parsed_attendance = normalized["attendance_raw"].map(parse_attendance_value)
    normalized["attendance_estimated"] = parsed_attendance.map(lambda value: value[0])
    normalized["attendance_parse_status"] = parsed_attendance.map(lambda value: value[1])
    normalized["start_date"] = normalized["start_ts"].dt.date
    normalized["end_date"] = normalized["end_ts"].dt.date
    normalized["is_multi_day_event"] = normalized["end_date"] > normalized["start_date"]
    normalized["detail_url"] = normalized["url_detalle_evento"]
    normalized["comments"] = normalized["comentarios"]
    normalized["category"] = normalized["categoria"]
    normalized["title"] = normalized["titulo"]
    normalized["source_row_number"] = normalized.index + 2
    return normalized[
        [
            "id",
            "title",
            "category",
            "start_ts",
            "end_ts_raw",
            "end_ts",
            "end_ts_correction_applied",
            "duration_minutes",
            "location_raw",
            "location_key",
            "attendance_raw",
            "attendance_estimated",
            "attendance_parse_status",
            "comments",
            "detail_url",
            "startday",
            "endday",
            "tipo_de_elemento",
            "ruta_de_acceso",
            "start_date",
            "end_date",
            "is_multi_day_event",
            "source_row_number",
        ]
    ].rename(columns={"id": "event_id"})


def build_event_location_mapping(
    locations_df: pd.DataFrame,
    *,
    stations_master: pd.DataFrame,
    alias_map: dict[str, str],
    non_station_codes: set[str],
) -> pd.DataFrame:
    station_reference = build_station_group_reference(stations_master)
    location_matrix = locations_df.copy().rename(columns={"ubicaciones": "location_raw"})
    station_columns = [column for column in location_matrix.columns if column != "location_raw"]

    records: list[dict[str, object]] = []
    for row in location_matrix.to_dict(orient="records"):
        location_raw = row["location_raw"]
        location_key = normalize_match_label(location_raw)
        marked_codes = [
            str(column)
            for column in station_columns
            if pd.notna(row[column]) and str(row[column]).strip() not in {"", "0", "0.0"}
        ]

        supported_rows: list[dict[str, object]] = []
        non_station_present: list[str] = []
        unknown_codes: list[str] = []
        for raw_code in marked_codes:
            canonical_code, alias_kind = canonicalize_station_code(
                raw_code,
                alias_map=alias_map,
            )
            if canonical_code in non_station_codes:
                non_station_present.append(canonical_code)
                continue

            station_match = station_reference[
                station_reference["station_abbrev"] == canonical_code
            ]
            if station_match.empty:
                unknown_codes.append(canonical_code or raw_code)
                continue

            station_row = station_match.iloc[0]
            supported_rows.append(
                {
                    "location_raw": location_raw,
                    "location_key": location_key,
                    "station_code_raw": raw_code,
                    "station_abbrev": canonical_code,
                    "station_join_key": station_row["station_join_key"],
                    "station_display_name": station_row["station_display_name"],
                    "station_group": station_row["station_group"],
                    "is_shared_between_lines": bool(station_row["is_shared_between_lines"]),
                    "line_count": int(station_row["line_count"]),
                    "mapping_confidence": (
                        "matrix_alias" if alias_kind == "alias" else "matrix_exact"
                    ),
                }
            )

        station_mapping_count = len(supported_rows)
        if supported_rows:
            for supported_row in supported_rows:
                supported_row["station_mapping_count"] = station_mapping_count
                supported_row["non_station_codes_present"] = serialize_list(
                    non_station_present
                )
                supported_row["unknown_station_codes_present"] = serialize_list(
                    unknown_codes
                )
                records.append(supported_row)
        else:
            records.append(
                {
                    "location_raw": location_raw,
                    "location_key": location_key,
                    "station_code_raw": pd.NA,
                    "station_abbrev": pd.NA,
                    "station_join_key": pd.NA,
                    "station_display_name": pd.NA,
                    "station_group": pd.NA,
                    "is_shared_between_lines": pd.NA,
                    "line_count": pd.NA,
                    "mapping_confidence": pd.NA,
                    "station_mapping_count": 0,
                    "non_station_codes_present": serialize_list(non_station_present),
                    "unknown_station_codes_present": serialize_list(unknown_codes),
                }
            )

    return pd.DataFrame(records)


def build_events_station_impact(
    events_master: pd.DataFrame,
    location_mapping: pd.DataFrame,
) -> pd.DataFrame:
    station_mapping = location_mapping[
        location_mapping["station_abbrev"].notna()
    ].copy()
    impacted = events_master.merge(
        station_mapping,
        on="location_key",
        how="left",
        suffixes=("", "_mapping"),
    )
    impacted["location_mapping_confidence"] = impacted["mapping_confidence"]
    impacted["has_station_mapping"] = impacted["station_abbrev"].notna()
    return impacted[
        impacted["has_station_mapping"]
    ][
        [
            "event_id",
            "title",
            "category",
            "start_ts",
            "end_ts",
            "start_date",
            "end_date",
            "duration_minutes",
            "location_raw",
            "location_key",
            "attendance_estimated",
            "attendance_parse_status",
            "station_abbrev",
            "station_join_key",
            "station_display_name",
            "station_group",
            "is_shared_between_lines",
            "station_mapping_count",
            "location_mapping_confidence",
            "non_station_codes_present",
            "unknown_station_codes_present",
        ]
    ].sort_values(["event_id", "station_abbrev"])


def build_events_station_daily(events_station_impact: pd.DataFrame) -> pd.DataFrame:
    daily_rows: list[dict[str, object]] = []
    for row in events_station_impact.to_dict(orient="records"):
        for active_date in expand_date_span(
            pd.Timestamp(row["start_ts"]),
            pd.Timestamp(row["end_ts"]),
        ):
            is_starting_day = active_date.date() == row["start_date"]
            is_ending_day = active_date.date() == row["end_date"]
            daily_rows.append(
                {
                    "service_date": active_date.date(),
                    "station_abbrev": row["station_abbrev"],
                    "station_join_key": row["station_join_key"],
                    "station_display_name": row["station_display_name"],
                    "active_event_count": 1,
                    "starting_event_count": int(is_starting_day),
                    "ending_event_count": int(is_ending_day),
                    "starting_estimated_attendance_sum": (
                        row["attendance_estimated"] if is_starting_day else 0
                    ),
                    "starting_unknown_attendance_count": int(
                        is_starting_day
                        and row["attendance_parse_status"] != "parsed"
                    ),
                    "high_impact_starting_event_count": int(
                        is_starting_day
                        and pd.notna(row["attendance_estimated"])
                        and int(row["attendance_estimated"])
                        >= HIGH_IMPACT_ATTENDANCE_THRESHOLD
                    ),
                }
            )

    if not daily_rows:
        return pd.DataFrame(
            columns=[
                "service_date",
                "station_abbrev",
                "station_join_key",
                "station_display_name",
                "active_event_count",
                "starting_event_count",
                "ending_event_count",
                "starting_estimated_attendance_sum",
                "starting_unknown_attendance_count",
                "high_impact_starting_event_count",
            ]
        )

    daily = pd.DataFrame(daily_rows)
    return (
        daily.groupby(
            ["service_date", "station_abbrev", "station_join_key", "station_display_name"],
            dropna=False,
            as_index=False,
        )
        .sum(numeric_only=True)
        .sort_values(["service_date", "station_abbrev"])
    )


def build_events_phase2a_series_daily(
    events_station_daily: pd.DataFrame,
    *,
    stations_master: pd.DataFrame,
) -> pd.DataFrame:
    station_series = stations_master[
        ["linea", "estacion", "station_abbrev", "station_join_key", "station_display_name"]
    ].drop_duplicates()
    station_group_line_count = (
        station_series.groupby("station_join_key", as_index=False)
        .agg(station_group_line_count=("linea", "nunique"))
    )
    join_ready = events_station_daily.merge(
        station_series,
        on=["station_join_key", "station_abbrev", "station_display_name"],
        how="left",
    )
    join_ready = join_ready.merge(
        station_group_line_count,
        on="station_join_key",
        how="left",
    )
    join_ready["shared_station_group_propagated"] = (
        join_ready["station_group_line_count"].fillna(1).astype(int) > 1
    )
    join_ready["propagation_rule"] = join_ready["shared_station_group_propagated"].map(
        lambda is_shared: (
            "broadcast_shared_station_group_to_member_lines"
            if is_shared
            else "direct_unique_station_group_to_single_line"
        )
    )
    join_ready["deduplication_weight"] = (
        1.0 / join_ready["station_group_line_count"].fillna(1).astype(float)
    )
    for metric in [
        "active_event_count",
        "starting_event_count",
        "ending_event_count",
        "starting_estimated_attendance_sum",
        "starting_unknown_attendance_count",
        "high_impact_starting_event_count",
    ]:
        join_ready[f"{metric}_deduplicated"] = (
            join_ready[metric] * join_ready["deduplication_weight"]
        )

    return join_ready[
        [
            "service_date",
            "linea",
            "estacion",
            "station_abbrev",
            "station_join_key",
            "station_display_name",
            "station_group_line_count",
            "shared_station_group_propagated",
            "propagation_rule",
            "deduplication_weight",
            "active_event_count",
            "active_event_count_deduplicated",
            "starting_event_count",
            "starting_event_count_deduplicated",
            "ending_event_count",
            "ending_event_count_deduplicated",
            "starting_estimated_attendance_sum",
            "starting_estimated_attendance_sum_deduplicated",
            "starting_unknown_attendance_count",
            "starting_unknown_attendance_count_deduplicated",
            "high_impact_starting_event_count",
            "high_impact_starting_event_count_deduplicated",
        ]
    ].sort_values(["service_date", "linea", "station_join_key"])


def build_events_mapping_report(
    events_master: pd.DataFrame,
    location_mapping: pd.DataFrame,
) -> pd.DataFrame:
    event_counts = (
        events_master.groupby(["location_raw", "location_key"], dropna=False)
        .agg(event_count=("event_id", "count"))
        .reset_index()
    )
    mapping_summary = (
        location_mapping.groupby(["location_raw", "location_key"], dropna=False)
        .agg(
            station_codes_raw=("station_code_raw", _unique_join),
            station_codes_canonical=("station_abbrev", _unique_join),
            station_mapping_count=("station_abbrev", lambda series: int(series.notna().sum())),
            non_station_codes_present=("non_station_codes_present", _unique_join),
            unknown_station_codes_present=("unknown_station_codes_present", _unique_join),
        )
        .reset_index()
    )
    mapping_summary_by_key = (
        location_mapping.groupby(["location_key"], dropna=False)
        .agg(
            normalized_station_codes_raw=("station_code_raw", _unique_join),
            normalized_station_codes_canonical=("station_abbrev", _unique_join),
            normalized_station_mapping_count=("station_abbrev", lambda series: int(series.notna().sum())),
            normalized_non_station_codes_present=("non_station_codes_present", _unique_join),
            normalized_unknown_station_codes_present=("unknown_station_codes_present", _unique_join),
        )
        .reset_index()
    )
    report = event_counts.merge(
        mapping_summary,
        on=["location_raw", "location_key"],
        how="left",
    )
    report = report.merge(mapping_summary_by_key, on="location_key", how="left")
    report["station_codes_raw"] = report["station_codes_raw"].fillna(
        report["normalized_station_codes_raw"]
    )
    report["station_codes_canonical"] = report["station_codes_canonical"].fillna(
        report["normalized_station_codes_canonical"]
    )
    report["station_mapping_count"] = report["station_mapping_count"].fillna(
        report["normalized_station_mapping_count"]
    )
    report["non_station_codes_present"] = report["non_station_codes_present"].fillna(
        report["normalized_non_station_codes_present"]
    )
    report["unknown_station_codes_present"] = report[
        "unknown_station_codes_present"
    ].fillna(report["normalized_unknown_station_codes_present"])
    report = report.drop(
        columns=[
            "normalized_station_codes_raw",
            "normalized_station_codes_canonical",
            "normalized_station_mapping_count",
            "normalized_non_station_codes_present",
            "normalized_unknown_station_codes_present",
        ]
    )
    exact_location_keys = set(location_mapping["location_raw"].dropna().astype(str).str.strip())
    normalized_location_keys = set(location_mapping["location_key"].dropna())
    report["exact_match_found"] = report["location_raw"].astype(str).str.strip().isin(
        exact_location_keys
    )
    report["normalized_match_found"] = report["location_key"].isin(normalized_location_keys)
    report["notes"] = report.apply(_build_mapping_note, axis=1)
    return report.sort_values(["event_count", "location_raw"], ascending=[False, True])


def _unique_join(series: pd.Series) -> str | None:
    values = sorted({str(value) for value in series.dropna() if str(value).strip()})
    if not values:
        return None
    return "|".join(values)


def _build_mapping_note(row: pd.Series) -> str | None:
    if not row["normalized_match_found"]:
        return "location_missing_in_mapping_sheet"
    if row["exact_match_found"] is False and row["normalized_match_found"] is True:
        return "normalized_text_match_only"
    if pd.notna(row["unknown_station_codes_present"]):
        return "unknown_station_codes_present"
    if (row["station_mapping_count"] or 0) > 1:
        return "multi_station_location"
    if pd.isna(row["station_codes_canonical"]):
        return "no_station_mapping_after_code_filter"
    return None
