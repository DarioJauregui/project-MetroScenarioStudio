from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from metro_demand_models.configuration import Settings, load_settings
from metro_demand_models.data.contracts import (
    OperationalOutputContract,
    WorkbookSourceContract,
    load_operational_output_contracts,
    load_workbook_source_contracts,
)
from metro_demand_models.data.io import read_table
from metro_demand_models.data.operations.common import (
    apply_station_abbrev_corrections,
    ensure_directory,
    normalize_match_label,
    resolve_workbook_path,
)
from metro_demand_models.data.operations.events import (
    build_event_location_mapping,
    build_events_mapping_report,
    build_events_phase2a_series_daily,
    build_events_station_daily,
    build_events_station_impact,
    inspect_event_sources,
    normalize_events_master,
)
from metro_demand_models.data.operations.incidents import (
    build_incidents_daily,
    build_incidents_mapping_report,
    inspect_incidents_history,
    normalize_incidents_history,
)
from metro_demand_models.data.operations.services import (
    build_services_line_daily,
    inspect_services_history,
    normalize_services_history,
)
from metro_demand_models.data.validation import validate_dataset_contract


@dataclass(frozen=True)
class OperationalBuildArtifacts:
    source_paths: dict[str, str]
    output_paths: dict[str, str]
    inspections: dict[str, dict[str, object]]
    row_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_operational_sources(
    settings: Settings | None = None,
) -> dict[str, dict[str, object]]:
    resolved_settings = settings or load_settings()
    workbook_contracts = load_workbook_source_contracts(resolved_settings)
    source_frames, source_paths = _load_raw_sources(resolved_settings, workbook_contracts)
    stations_master = _load_stations_master(resolved_settings)

    operations_settings = resolved_settings["operations"]
    alias_map_events = {
        str(key): str(value)
        for key, value in operations_settings["events"]["location_code_aliases"].items()
    }
    alias_map_incidents = {
        str(key): str(value)
        for key, value in operations_settings["incidents"]["station_code_aliases"].items()
    }
    non_station_codes = {
        str(code).upper() for code in operations_settings["events"]["non_station_codes"]
    }
    line_values = {
        _normalize_line_key(value): str(value)
        for value in operations_settings["incidents"]["line_location_values"]
    }
    depot_keywords = tuple(str(value) for value in operations_settings["incidents"]["depot_keywords"])
    crossing_keywords = tuple(
        str(value) for value in operations_settings["incidents"]["crossing_keywords"]
    )
    network_keywords = tuple(
        str(value) for value in operations_settings["incidents"]["network_keywords"]
    )
    rollover_threshold_minutes = _parse_hhmmss_to_minutes(
        operations_settings["service_day_rollover_threshold"]
    )

    services_inspection = inspect_services_history(
        source_frames["services_history"],
        dataset_path=source_paths["services_history"],
        contract=workbook_contracts["services_history"],
        rollover_threshold_minutes=rollover_threshold_minutes,
    )
    events_inspection = inspect_event_sources(
        source_frames["events_calendar"],
        source_frames["event_locations"],
        dataset_path=source_paths["events_calendar"],
        events_contract=workbook_contracts["events_calendar"],
        locations_contract=workbook_contracts["event_locations"],
        alias_map=alias_map_events,
        non_station_codes=non_station_codes,
        stations_master=stations_master,
    )
    incidents_inspection = inspect_incidents_history(
        source_frames["incidents_history"],
        dataset_path=source_paths["incidents_history"],
        contract=workbook_contracts["incidents_history"],
        stations_master=stations_master,
        alias_map=alias_map_incidents,
        line_values=line_values,
        depot_keywords=depot_keywords,
        crossing_keywords=crossing_keywords,
        network_keywords=network_keywords,
    )
    return {
        "services_history": services_inspection.to_dict(),
        "events_calendar": events_inspection.to_dict(),
        "incidents_history": incidents_inspection.to_dict(),
    }


def build_operational_datasets(
    settings: Settings | None = None,
) -> OperationalBuildArtifacts:
    resolved_settings = settings or load_settings()
    workbook_contracts = load_workbook_source_contracts(resolved_settings)
    output_contracts = load_operational_output_contracts(resolved_settings)
    source_frames, source_paths = _load_raw_sources(resolved_settings, workbook_contracts)
    inspections = inspect_operational_sources(resolved_settings)
    stations_master = _load_stations_master(resolved_settings)

    operations_settings = resolved_settings["operations"]
    alias_map_events = {
        str(key): str(value)
        for key, value in operations_settings["events"]["location_code_aliases"].items()
    }
    alias_map_incidents = {
        str(key): str(value)
        for key, value in operations_settings["incidents"]["station_code_aliases"].items()
    }
    non_station_codes = {
        str(code).upper() for code in operations_settings["events"]["non_station_codes"]
    }
    line_values = {
        _normalize_line_key(value): str(value)
        for value in operations_settings["incidents"]["line_location_values"]
    }
    depot_keywords = tuple(str(value) for value in operations_settings["incidents"]["depot_keywords"])
    crossing_keywords = tuple(
        str(value) for value in operations_settings["incidents"]["crossing_keywords"]
    )
    network_keywords = tuple(
        str(value) for value in operations_settings["incidents"]["network_keywords"]
    )
    rollover_threshold_minutes = _parse_hhmmss_to_minutes(
        operations_settings["service_day_rollover_threshold"]
    )

    services_daily = normalize_services_history(
        source_frames["services_history"],
        rollover_threshold_minutes=rollover_threshold_minutes,
    )
    services_line_daily = build_services_line_daily(services_daily)

    events_normalized = normalize_events_master(source_frames["events_calendar"])
    event_location_mapping = build_event_location_mapping(
        source_frames["event_locations"],
        stations_master=stations_master,
        alias_map=alias_map_events,
        non_station_codes=non_station_codes,
    )
    events_station_impact = build_events_station_impact(
        events_normalized,
        event_location_mapping,
    )
    events_station_daily = build_events_station_daily(events_station_impact)
    events_phase2a_series_daily = build_events_phase2a_series_daily(
        events_station_daily,
        stations_master=stations_master,
    )
    events_mapping_report = build_events_mapping_report(
        events_normalized,
        event_location_mapping,
    )

    incidents_normalized = normalize_incidents_history(
        source_frames["incidents_history"],
        stations_master=stations_master,
        alias_map=alias_map_incidents,
        line_values=line_values,
        depot_keywords=depot_keywords,
        crossing_keywords=crossing_keywords,
        network_keywords=network_keywords,
    )
    incidents_daily = build_incidents_daily(incidents_normalized)
    incidents_mapping_report = build_incidents_mapping_report(incidents_normalized)

    inspection_summary = _build_inspection_summary(inspections)

    output_frames: dict[str, pd.DataFrame] = {
        "services_history_daily": services_daily,
        "services_line_daily": services_line_daily,
        "events_normalized": events_normalized,
        "events_station_impact": events_station_impact,
        "events_station_daily": events_station_daily,
        "events_phase2a_series_daily": events_phase2a_series_daily,
        "incidents_normalized": incidents_normalized,
        "incidents_daily": incidents_daily,
        "events_mapping_report": events_mapping_report,
        "incidents_mapping_report": incidents_mapping_report,
        "inspection_summary": inspection_summary,
    }

    output_paths: dict[str, str] = {}
    for name, frame in output_frames.items():
        contract = output_contracts[name]
        validate_dataset_contract(
            frame,
            required_columns=contract.required_columns,
            unique_key=contract.unique_key,
            dataset_name=name,
        )
        target_path = _write_output_dataset(
            resolved_settings,
            contract,
            frame,
        )
        output_paths[name] = str(target_path)

    return OperationalBuildArtifacts(
        source_paths=source_paths,
        output_paths=output_paths,
        inspections=inspections,
        row_counts={name: int(len(frame)) for name, frame in output_frames.items()},
    )


def _load_raw_sources(
    settings: Settings,
    contracts: dict[str, WorkbookSourceContract],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    frames: dict[str, pd.DataFrame] = {}
    paths: dict[str, str] = {}
    for name, contract in contracts.items():
        workbook_path = resolve_workbook_path(settings, contract)
        dataframe = read_table(workbook_path, sheet_name=contract.sheet_name)
        dataframe.columns = dataframe.columns
        from metro_demand_models.data.operations.common import normalize_source_dataframe, validate_workbook_source_columns

        normalized = normalize_source_dataframe(dataframe)
        validate_workbook_source_columns(normalized, contract)
        frames[name] = normalized
        paths[name] = str(workbook_path)
    return frames, paths


def _load_stations_master(settings: Settings) -> pd.DataFrame:
    stations_master_path = Path(settings["resolved_paths"]["stations_master_file"])
    stations_master = read_table(stations_master_path)
    corrections = {
        str(key): str(value)
        for key, value in settings["operations"]["naming"]["station_abbrev_corrections"].items()
    }
    return apply_station_abbrev_corrections(
        stations_master,
        corrections=corrections,
    )


def _write_output_dataset(
    settings: Settings,
    contract: OperationalOutputContract,
    dataframe: pd.DataFrame,
) -> Path:
    output_dir = ensure_directory(contract.resolve_path(settings))
    suffix = ".csv" if contract.granularity == "report" else ".parquet"
    target_path = output_dir / f"{contract.name}{suffix}"
    if suffix == ".csv":
        dataframe.to_csv(target_path, index=False, encoding="utf-8")
    else:
        dataframe.to_parquet(target_path, index=False)
    return target_path


def _build_inspection_summary(
    inspections: dict[str, dict[str, object]]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for source_name, payload in inspections.items():
        if source_name == "events_calendar":
            rows.extend(
                _inspection_rows_from_payload(
                    source_name,
                    payload["events_dataset"],
                    note_fields={
                        "event_rows_with_exact_mapping": payload["event_rows_with_exact_mapping"],
                        "event_rows_with_normalized_mapping": payload["event_rows_with_normalized_mapping"],
                        "event_rows_with_negative_duration": payload["event_rows_with_negative_duration"],
                    },
                )
            )
            rows.extend(
                _inspection_rows_from_payload(
                    "event_locations",
                    payload["locations_dataset"],
                    note_fields={
                        "mapping_rows_with_multiple_station_codes": payload["mapping_rows_with_multiple_station_codes"],
                        "mapping_rows_with_unknown_codes": payload["mapping_rows_with_unknown_codes"],
                    },
                )
            )
            continue

        dataset_payload = payload["dataset"]
        note_fields = {
            key: value
            for key, value in payload.items()
            if key != "dataset"
        }
        rows.extend(
            _inspection_rows_from_payload(
                source_name,
                dataset_payload,
                note_fields=note_fields,
            )
        )
    return pd.DataFrame(rows)


def _inspection_rows_from_payload(
    source_name: str,
    dataset_payload: dict[str, object],
    *,
    note_fields: dict[str, object],
) -> list[dict[str, object]]:
    date_ranges = dataset_payload.get("date_ranges", {})
    if date_ranges:
        first_date_range = next(iter(date_ranges.values()))
        date_min = first_date_range.get("min")
        date_max = first_date_range.get("max")
    else:
        date_min = None
        date_max = None

    return [
        {
            "source_name": source_name,
            "sheet_name": dataset_payload["dataset_name"],
            "row_count": dataset_payload["row_count"],
            "column_count": dataset_payload["column_count"],
            "date_min": date_min,
            "date_max": date_max,
            "duplicate_count": dataset_payload["duplicate_count"],
            "notes": _serialize_notes(note_fields),
        }
    ]


def _serialize_notes(values: dict[str, object]) -> str | None:
    filtered = {
        key: value
        for key, value in values.items()
        if value is not None
    }
    if not filtered:
        return None
    return "; ".join(f"{key}={value}" for key, value in filtered.items())


def _parse_hhmmss_to_minutes(value: object) -> int:
    parts = str(value).split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid HH:MM:SS value: '{value}'.")
    hours, minutes, seconds = (int(part) for part in parts)
    if seconds:
        raise ValueError("Rollover threshold must not include seconds.")
    return (hours * 60) + minutes


def _normalize_line_key(value: object) -> str:
    return normalize_match_label(value)
