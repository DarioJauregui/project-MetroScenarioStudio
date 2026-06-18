from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time
from pathlib import Path
import re
import unicodedata

import pandas as pd

from metro_demand_models.configuration import Settings, get_path
from metro_demand_models.data.contracts import WorkbookSourceContract
from metro_demand_models.data.io import read_table
from metro_demand_models.data.validation import validate_required_columns


ZERO_WIDTH_TRANSLATION = {
    ord("\u200b"): None,
    ord("\ufeff"): None,
}


@dataclass(frozen=True)
class ParsedTimeValue:
    time_string: str | None
    service_axis_minutes: int | None
    day_offset: int | None


def normalize_match_label(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.translate(ZERO_WIDTH_TRANSLATION)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return " ".join(text.lower().strip().split())


def to_snake_case(value: object) -> str:
    return normalize_match_label(value).replace(" ", "_")


def clean_blank_strings(dataframe: pd.DataFrame) -> pd.DataFrame:
    cleaned = dataframe.copy()
    object_columns = cleaned.select_dtypes(include=["object", "string"]).columns
    for column in object_columns:
        cleaned[column] = cleaned[column].map(_clean_string_value)
    return cleaned


def normalize_source_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    renamed = dataframe.copy()
    renamed.columns = [to_snake_case(column) for column in renamed.columns]
    return clean_blank_strings(renamed)


def validate_workbook_source_columns(
    dataframe: pd.DataFrame,
    contract: WorkbookSourceContract,
) -> None:
    expected_columns = [to_snake_case(column) for column in contract.required_columns]
    validate_required_columns(dataframe, expected_columns)


def resolve_workbook_path(
    settings: Settings,
    contract: WorkbookSourceContract,
) -> Path:
    base_directory = get_path(settings, contract.path_ref)
    matches = sorted(
        path
        for path in base_directory.glob(contract.file_glob)
        if path.is_file() and not path.name.startswith("~$")
    )
    if not matches:
        raise FileNotFoundError(
            f"No workbook found for pattern '{contract.file_glob}' in '{base_directory}'."
        )
    if len(matches) > 1:
        joined = ", ".join(str(path.name) for path in matches)
        raise FileExistsError(
            f"Multiple workbooks match '{contract.file_glob}' in '{base_directory}': "
            f"{joined}."
        )
    return matches[0]


def load_workbook_sheet(
    settings: Settings,
    contract: WorkbookSourceContract,
) -> tuple[Path, pd.DataFrame]:
    workbook_path = resolve_workbook_path(settings, contract)
    dataframe = read_table(workbook_path, sheet_name=contract.sheet_name)
    normalized = normalize_source_dataframe(dataframe)
    validate_workbook_source_columns(normalized, contract)
    return workbook_path, normalized


def parse_time_value(
    value: object,
    *,
    rollover_threshold_minutes: int,
) -> ParsedTimeValue:
    if value is None or pd.isna(value):
        return ParsedTimeValue(None, None, None)

    parsed_time = _coerce_time(value)
    if parsed_time is None:
        return ParsedTimeValue(None, None, None)

    base_minutes = parsed_time.hour * 60 + parsed_time.minute
    day_offset = 1 if base_minutes < rollover_threshold_minutes else 0
    service_axis_minutes = base_minutes + (day_offset * 1440)
    return ParsedTimeValue(
        time_string=parsed_time.strftime("%H:%M:%S"),
        service_axis_minutes=service_axis_minutes,
        day_offset=day_offset,
    )


def parse_attendance_value(value: object) -> tuple[int | None, str]:
    if value is None or pd.isna(value):
        return None, "missing"

    raw_value = _clean_string_value(value)
    if raw_value is None:
        return None, "missing"

    compact = raw_value.replace(".", "").replace(" ", "")
    match = re.search(r"(\d+)", compact)
    if not match:
        return None, "unparseable_text"

    return int(match.group(1)), "parsed"


def build_station_group_reference(stations_master: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        stations_master.groupby("station_abbrev", dropna=False)
        .agg(
            station_join_key=("station_join_key", "first"),
            station_group=("station_group", "first"),
            station_display_name=("station_display_name", "first"),
            line_count=("linea", "nunique"),
        )
        .reset_index()
    )
    grouped["is_shared_between_lines"] = grouped["line_count"] > 1
    return grouped


def apply_station_abbrev_corrections(
    stations_master: pd.DataFrame,
    *,
    corrections: dict[str, str] | None = None,
) -> pd.DataFrame:
    normalized = stations_master.copy()
    normalized["station_abbrev_master_raw"] = normalized["station_abbrev"]
    correction_lookup = {
        str(source).upper(): str(target).upper()
        for source, target in (corrections or {}).items()
    }
    def correct_code(value: object) -> object:
        if value is None or pd.isna(value):
            return value
        return correction_lookup.get(str(value).upper(), str(value).upper())

    normalized["station_abbrev"] = normalized["station_abbrev"].map(correct_code)
    return normalized


def canonicalize_station_code(
    raw_code: object,
    *,
    alias_map: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    if raw_code is None or pd.isna(raw_code):
        return None, "missing"

    cleaned = _clean_string_value(raw_code)
    if cleaned is None:
        return None, "missing"

    code = str(cleaned).strip()
    alias_lookup = {str(key).upper(): str(value).upper() for key, value in (alias_map or {}).items()}
    if code.upper() in alias_lookup:
        return alias_lookup[code.upper()], "alias"
    return code.upper(), "exact"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def expand_date_span(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[pd.Timestamp]:
    if pd.isna(start_ts) or pd.isna(end_ts):
        return []
    return list(pd.date_range(start_ts.normalize(), end_ts.normalize(), freq="D"))


def serialize_list(values: Iterable[object]) -> str | None:
    normalized = [str(value) for value in values if value is not None and str(value) != ""]
    if not normalized:
        return None
    return "|".join(normalized)


def _clean_string_value(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).translate(ZERO_WIDTH_TRANSLATION).strip()
    return text or None


def _coerce_time(value: object) -> time | None:
    if isinstance(value, time):
        return value.replace(microsecond=0)

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().time().replace(microsecond=0)

    cleaned = _clean_string_value(value)
    if cleaned is None:
        return None

    for fmt in ("%H:%M:%S", "%H:%M"):
        parsed = pd.to_datetime(cleaned, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return parsed.to_pydatetime().time().replace(microsecond=0)

    parsed_any = pd.to_datetime(cleaned, errors="coerce")
    if pd.isna(parsed_any):
        return None
    return parsed_any.to_pydatetime().time().replace(microsecond=0)
