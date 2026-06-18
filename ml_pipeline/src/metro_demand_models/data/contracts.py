from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metro_demand_models.configuration import Settings, get_path


@dataclass(frozen=True)
class DatasetContract:
    name: str
    path_ref: str
    granularity: str
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...] = ()
    unique_key: tuple[str, ...] = ()
    timestamp_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()

    def resolve_path(self, settings: Settings) -> Path:
        return get_path(settings, self.path_ref)


@dataclass(frozen=True)
class JoinContract:
    name: str
    left_dataset: str
    right_dataset: str
    left_keys: tuple[str, ...]
    right_keys: tuple[str, ...]
    join_type: str
    required: bool
    right_unique: bool
    missing_policy: str
    pre_aggregation: str | None = None


@dataclass(frozen=True)
class ModelingBaseContract:
    name: str
    phase_scope: str | None
    source_dataset: str
    prediction_unit: str
    service_date_column: str
    target_column: str
    identifier_columns: tuple[str, ...]
    temporal_columns: tuple[str, ...]
    feature_columns: tuple[str, ...]
    conditional_feature_columns: tuple[str, ...]
    support_columns: tuple[str, ...]
    excluded_from_direct_modeling: tuple[str, ...]


@dataclass(frozen=True)
class ServiceDayPolicy:
    timezone: str
    policy: str
    boundary_hour: int
    boundary_minute: int
    description: str


@dataclass(frozen=True)
class SeriesContract:
    series_grain: str
    series_id_column: str
    natural_key_columns: tuple[str, ...]
    series_id_format: str
    series_label_columns: tuple[str, ...]
    why_station_alone_is_not_stable: str
    why_cod_eq_is_not_stable: str


@dataclass(frozen=True)
class FutureGranularContract:
    name: str
    status: str
    source_dataset: str
    prediction_unit: str
    series_id_column: str
    time_key_column: str
    example_interval: str
    description: str


@dataclass(frozen=True)
class WorkbookSourceContract:
    name: str
    path_ref: str
    file_glob: str
    sheet_name: str
    granularity: str
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...] = ()
    unique_key: tuple[str, ...] = ()

    def resolve_path(self, settings: Settings) -> Path:
        return get_path(settings, self.path_ref)


@dataclass(frozen=True)
class OperationalOutputContract:
    name: str
    path_ref: str
    granularity: str
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...] = ()
    unique_key: tuple[str, ...] = ()

    def resolve_path(self, settings: Settings) -> Path:
        return get_path(settings, self.path_ref)


def _tuple_of_strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()

    return tuple(str(value) for value in values)


def _get_section(settings: Settings, *keys: str) -> dict[str, Any]:
    current: Any = settings
    for key in keys:
        if key not in current:
            joined_keys = ".".join(keys)
            raise KeyError(f"Missing configuration section '{joined_keys}'.")
        current = current[key]

    if not isinstance(current, dict):
        joined_keys = ".".join(keys)
        raise TypeError(f"Configuration section '{joined_keys}' must be a mapping.")

    return current


def load_dataset_contracts(settings: Settings) -> dict[str, DatasetContract]:
    dataset_sections = _get_section(settings, "datasets")
    contracts: dict[str, DatasetContract] = {}

    for name, values in dataset_sections.items():
        if not isinstance(values, dict):
            raise TypeError(f"Dataset section '{name}' must be a mapping.")

        contracts[name] = DatasetContract(
            name=name,
            path_ref=str(values["path_ref"]),
            granularity=str(values["granularity"]),
            required_columns=_tuple_of_strings(values.get("required_columns")),
            optional_columns=_tuple_of_strings(values.get("optional_columns")),
            unique_key=_tuple_of_strings(values.get("unique_key")),
            timestamp_columns=_tuple_of_strings(values.get("timestamp_columns")),
            date_columns=_tuple_of_strings(values.get("date_columns")),
        )

    return contracts


def load_join_contracts(settings: Settings) -> dict[str, JoinContract]:
    join_sections = _get_section(settings, "modeling", "joins")
    contracts: dict[str, JoinContract] = {}

    for name, values in join_sections.items():
        if not isinstance(values, dict):
            raise TypeError(f"Join section '{name}' must be a mapping.")

        contracts[name] = JoinContract(
            name=name,
            left_dataset=str(values["left_dataset"]),
            right_dataset=str(values["right_dataset"]),
            left_keys=_tuple_of_strings(values.get("left_keys")),
            right_keys=_tuple_of_strings(values.get("right_keys")),
            join_type=str(values["join_type"]),
            required=bool(values["required"]),
            right_unique=bool(values["right_unique"]),
            missing_policy=str(values["missing_policy"]),
            pre_aggregation=(
                None
                if values.get("pre_aggregation") is None
                else str(values["pre_aggregation"])
            ),
        )

    return contracts


def load_modeling_base_contract(settings: Settings) -> ModelingBaseContract:
    values = _get_section(settings, "modeling", "base_dataset")

    return ModelingBaseContract(
        name=str(values["name"]),
        phase_scope=(
            None if values.get("phase_scope") is None else str(values["phase_scope"])
        ),
        source_dataset=str(values["source_dataset"]),
        prediction_unit=str(values["prediction_unit"]),
        service_date_column=str(values["service_date_column"]),
        target_column=str(values["target_column"]),
        identifier_columns=_tuple_of_strings(values.get("identifier_columns")),
        temporal_columns=_tuple_of_strings(values.get("temporal_columns")),
        feature_columns=_tuple_of_strings(values.get("feature_columns")),
        conditional_feature_columns=_tuple_of_strings(
            values.get("conditional_feature_columns")
        ),
        support_columns=_tuple_of_strings(values.get("support_columns")),
        excluded_from_direct_modeling=_tuple_of_strings(
            values.get("excluded_from_direct_modeling")
        ),
    )


def load_service_day_policy(settings: Settings) -> ServiceDayPolicy:
    values = _get_section(settings, "modeling", "service_day")

    return ServiceDayPolicy(
        timezone=str(values["timezone"]),
        policy=str(values["policy"]),
        boundary_hour=int(values["boundary_hour"]),
        boundary_minute=int(values["boundary_minute"]),
        description=str(values["description"]),
    )


def load_series_contract(settings: Settings) -> SeriesContract:
    values = _get_section(settings, "modeling", "series")

    return SeriesContract(
        series_grain=str(values["series_grain"]),
        series_id_column=str(values["series_id_column"]),
        natural_key_columns=_tuple_of_strings(values.get("natural_key_columns")),
        series_id_format=str(values["series_id_format"]),
        series_label_columns=_tuple_of_strings(values.get("series_label_columns")),
        why_station_alone_is_not_stable=str(
            values["why_station_alone_is_not_stable"]
        ),
        why_cod_eq_is_not_stable=str(values["why_cod_eq_is_not_stable"]),
    )


def load_future_granular_contract(settings: Settings) -> FutureGranularContract:
    values = _get_section(settings, "modeling", "future_granular_dataset")

    return FutureGranularContract(
        name=str(values["name"]),
        status=str(values["status"]),
        source_dataset=str(values["source_dataset"]),
        prediction_unit=str(values["prediction_unit"]),
        series_id_column=str(values["series_id_column"]),
        time_key_column=str(values["time_key_column"]),
        example_interval=str(values["example_interval"]),
        description=str(values["description"]),
    )


def load_workbook_source_contracts(settings: Settings) -> dict[str, WorkbookSourceContract]:
    source_sections = _get_section(settings, "operations", "sources")
    contracts: dict[str, WorkbookSourceContract] = {}

    for name, values in source_sections.items():
        if not isinstance(values, dict):
            raise TypeError(f"Operations source section '{name}' must be a mapping.")

        contracts[name] = WorkbookSourceContract(
            name=name,
            path_ref=str(values["path_ref"]),
            file_glob=str(values["file_glob"]),
            sheet_name=str(values["sheet_name"]),
            granularity=str(values["granularity"]),
            required_columns=_tuple_of_strings(values.get("required_columns")),
            optional_columns=_tuple_of_strings(values.get("optional_columns")),
            unique_key=_tuple_of_strings(values.get("unique_key")),
        )

    return contracts


def load_operational_output_contracts(
    settings: Settings,
) -> dict[str, OperationalOutputContract]:
    output_sections = _get_section(settings, "operations", "outputs")
    contracts: dict[str, OperationalOutputContract] = {}

    for name, values in output_sections.items():
        if not isinstance(values, dict):
            raise TypeError(f"Operations output section '{name}' must be a mapping.")

        contracts[name] = OperationalOutputContract(
            name=name,
            path_ref=str(values["path_ref"]),
            granularity=str(values["granularity"]),
            required_columns=_tuple_of_strings(values.get("required_columns")),
            optional_columns=_tuple_of_strings(values.get("optional_columns")),
            unique_key=_tuple_of_strings(values.get("unique_key")),
        )

    return contracts
