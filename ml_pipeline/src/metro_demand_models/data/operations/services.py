from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from metro_demand_models.data.contracts import WorkbookSourceContract
from metro_demand_models.data.inspection import DatasetInspection, inspect_dataframe
from metro_demand_models.data.operations.common import parse_time_value


@dataclass(frozen=True)
class ServicesInspection:
    dataset: DatasetInspection
    rows_with_planned_xml: int
    rows_with_used_xml: int
    rows_with_both_xml: int
    rows_with_xml_override: int
    rows_with_line_2_end_time: int
    rows_with_overnight_end: int

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dataset"] = self.dataset.to_dict()
        return payload


def inspect_services_history(
    dataframe: pd.DataFrame,
    *,
    dataset_path: str,
    contract: WorkbookSourceContract,
    rollover_threshold_minutes: int,
) -> ServicesInspection:
    inspection = inspect_dataframe(
        dataframe,
        dataset_name=contract.name,
        dataset_path=dataset_path,
        duplicate_key=("fecha",),
        date_columns=("fecha",),
    )
    normalized = normalize_services_history(
        dataframe,
        rollover_threshold_minutes=rollover_threshold_minutes,
    )
    return ServicesInspection(
        dataset=inspection,
        rows_with_planned_xml=int(normalized["planned_service_xml_name"].notna().sum()),
        rows_with_used_xml=int(normalized["used_service_xml_name"].notna().sum()),
        rows_with_both_xml=int(
            (
                normalized["planned_service_xml_name"].notna()
                & normalized["used_service_xml_name"].notna()
            ).sum()
        ),
        rows_with_xml_override=int(normalized["used_service_override_flag"].sum()),
        rows_with_line_2_end_time=int(normalized["line_2_end_time"].notna().sum()),
        rows_with_overnight_end=int(
            (
                normalized["commercial_end_day_offset"].notna()
                & normalized["commercial_end_day_offset"].eq(1)
            ).sum()
        ),
    )


def normalize_services_history(
    dataframe: pd.DataFrame,
    *,
    rollover_threshold_minutes: int,
) -> pd.DataFrame:
    normalized = dataframe.copy()
    normalized = normalized.sort_values("fecha").reset_index(drop=True)

    planned_time = normalized["inicio_serv_comercial"].map(
        lambda value: parse_time_value(
            value,
            rollover_threshold_minutes=rollover_threshold_minutes,
        )
    )
    line_1_end = normalized["fin_l1_serv_comercial"].map(
        lambda value: parse_time_value(
            value,
            rollover_threshold_minutes=rollover_threshold_minutes,
        )
    )
    line_2_end = normalized["fin_l2_serv_comercial"].map(
        lambda value: parse_time_value(
            value,
            rollover_threshold_minutes=rollover_threshold_minutes,
        )
    )

    normalized["service_date"] = pd.to_datetime(normalized["fecha"]).dt.date
    normalized["service_name_raw"] = normalized["servicio"]
    normalized["planned_service_xml_name"] = _clean_service_xml_name(
        normalized["archivo_xml_planificado"]
    )
    normalized["used_service_xml_name"] = _clean_service_xml_name(
        normalized["archivo_xml_usado"]
    )
    normalized["planned_service_code"] = normalized["planned_service_xml_name"].map(
        _extract_service_code_from_xml
    )
    normalized["used_service_code"] = normalized["used_service_xml_name"].map(
        _extract_service_code_from_xml
    )
    normalized["used_service_override_flag"] = (
        normalized["planned_service_xml_name"].notna()
        & normalized["used_service_xml_name"].notna()
        & (
            normalized["planned_service_xml_name"]
            != normalized["used_service_xml_name"]
        )
    )

    normalized["commercial_start_time"] = planned_time.map(lambda value: value.time_string)
    normalized["commercial_start_minutes"] = planned_time.map(
        lambda value: value.service_axis_minutes
    )
    normalized["commercial_start_day_offset"] = planned_time.map(
        lambda value: value.day_offset
    )

    normalized["line_1_end_time"] = line_1_end.map(lambda value: value.time_string)
    normalized["line_1_end_minutes"] = line_1_end.map(
        lambda value: value.service_axis_minutes
    )
    normalized["line_1_end_day_offset"] = line_1_end.map(lambda value: value.day_offset)

    normalized["line_2_end_time"] = line_2_end.map(lambda value: value.time_string)
    normalized["line_2_end_minutes"] = line_2_end.map(
        lambda value: value.service_axis_minutes
    )
    normalized["line_2_end_day_offset"] = line_2_end.map(lambda value: value.day_offset)

    effective_end = normalized.apply(_compute_effective_end, axis=1, result_type="expand")
    normalized["commercial_end_time_effective"] = effective_end["time"]
    normalized["commercial_end_minutes"] = effective_end["minutes"]
    normalized["commercial_end_day_offset"] = effective_end["day_offset"]
    normalized["commercial_end_source"] = effective_end["source"]

    normalized["service_description"] = normalized["descripcion_servicio"]
    normalized["event_label"] = normalized["evento"]
    normalized["extraordinary_demand"] = normalized["demanda_extraordinaria"]
    normalized["comments"] = normalized["comentarios"]
    normalized["comments_for_ing"] = normalized["comentarios_para_ing"]

    normalized["source_row_number"] = normalized.index + 2

    return normalized[
        [
            "service_date",
            "service_name_raw",
            "planned_service_xml_name",
            "used_service_xml_name",
            "planned_service_code",
            "used_service_code",
            "used_service_override_flag",
            "commercial_start_time",
            "commercial_start_minutes",
            "commercial_start_day_offset",
            "line_1_end_time",
            "line_1_end_minutes",
            "line_1_end_day_offset",
            "line_2_end_time",
            "line_2_end_minutes",
            "line_2_end_day_offset",
            "commercial_end_time_effective",
            "commercial_end_minutes",
            "commercial_end_day_offset",
            "commercial_end_source",
            "service_description",
            "event_label",
            "extraordinary_demand",
            "comments",
            "comments_for_ing",
            "source_row_number",
        ]
    ]


def build_services_line_daily(normalized_daily: pd.DataFrame) -> pd.DataFrame:
    line_frames: list[pd.DataFrame] = []
    for line_name, prefix in (("LINEA 1", "line_1"), ("LINEA 2", "line_2")):
        frame = normalized_daily[
            normalized_daily[f"{prefix}_end_time"].notna()
        ].copy()
        frame["linea"] = line_name
        frame["line_end_time"] = frame[f"{prefix}_end_time"]
        frame["line_end_minutes"] = frame[f"{prefix}_end_minutes"]
        frame["line_end_day_offset"] = frame[f"{prefix}_end_day_offset"]
        line_frames.append(
            frame[
                [
                    "service_date",
                    "linea",
                    "commercial_start_time",
                    "commercial_start_minutes",
                    "commercial_start_day_offset",
                    "line_end_time",
                    "line_end_minutes",
                    "line_end_day_offset",
                    "service_name_raw",
                    "planned_service_xml_name",
                    "used_service_xml_name",
                    "service_description",
                    "event_label",
                ]
            ]
        )

    if not line_frames:
        return pd.DataFrame(
            columns=[
                "service_date",
                "linea",
                "commercial_start_time",
                "commercial_start_minutes",
                "commercial_start_day_offset",
                "line_end_time",
                "line_end_minutes",
                "line_end_day_offset",
                "service_name_raw",
                "planned_service_xml_name",
                "used_service_xml_name",
                "service_description",
                "event_label",
            ]
        )

    return pd.concat(line_frames, ignore_index=True).sort_values(
        ["service_date", "linea"]
    )


def _clean_service_xml_name(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.replace({"": pd.NA})
    return cleaned


def _extract_service_code_from_xml(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value).split("_", maxsplit=1)[0].lower()


def _compute_effective_end(row: pd.Series) -> pd.Series:
    candidates = [
        ("line_1", row["line_1_end_minutes"], row["line_1_end_time"], row["line_1_end_day_offset"]),
        ("line_2", row["line_2_end_minutes"], row["line_2_end_time"], row["line_2_end_day_offset"]),
    ]
    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate[1] is not None and not pd.isna(candidate[1])
    ]
    if not valid_candidates:
        return pd.Series(
            {
                "time": pd.NA,
                "minutes": pd.NA,
                "day_offset": pd.NA,
                "source": pd.NA,
            }
        )

    selected = max(valid_candidates, key=lambda item: item[1])
    return pd.Series(
        {
            "time": selected[2],
            "minutes": selected[1],
            "day_offset": selected[3],
            "source": selected[0],
        }
    )
