from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd


def ensure_files_exist(file_paths: Sequence[Path | str]) -> list[Path]:
    resolved_paths = [Path(file_path) for file_path in file_paths]
    missing_paths = [path for path in resolved_paths if not path.exists()]
    if missing_paths:
        missing_list = ", ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(f"Missing required input files: {missing_list}.")

    return resolved_paths


def find_missing_columns(
    dataframe: pd.DataFrame,
    required_columns: Iterable[str],
) -> list[str]:
    required = list(required_columns)
    return [column for column in required if column not in dataframe.columns]


def validate_required_columns(
    dataframe: pd.DataFrame,
    required_columns: Iterable[str],
) -> None:
    missing_columns = find_missing_columns(dataframe, required_columns)
    if missing_columns:
        missing_list = ", ".join(missing_columns)
        raise ValueError(f"Missing required columns: {missing_list}.")


def validate_non_null_columns(
    dataframe: pd.DataFrame,
    required_columns: Iterable[str],
    *,
    dataset_name: str = "dataset",
) -> None:
    required = list(required_columns)
    null_columns = [
        column
        for column in required
        if column in dataframe.columns and dataframe[column].isna().any()
    ]
    if null_columns:
        null_list = ", ".join(null_columns)
        raise ValueError(
            f"Columns expected to be non-null in '{dataset_name}' contain null values: "
            f"{null_list}."
        )


def validate_unique_key(
    dataframe: pd.DataFrame,
    key_columns: Iterable[str],
    *,
    dataset_name: str = "dataset",
) -> None:
    keys = list(key_columns)
    if not keys:
        return

    validate_required_columns(dataframe, keys)
    duplicate_count = int(dataframe.duplicated(subset=keys).sum())
    if duplicate_count:
        joined_keys = ", ".join(keys)
        raise ValueError(
            f"Dataset '{dataset_name}' contains {duplicate_count} duplicated rows for key "
            f"[{joined_keys}]."
        )


def validate_dataset_contract(
    dataframe: pd.DataFrame,
    *,
    required_columns: Iterable[str],
    unique_key: Iterable[str] | None = None,
    non_null_key_columns: Iterable[str] | None = None,
    dataset_name: str = "dataset",
) -> None:
    validate_required_columns(dataframe, required_columns)

    if unique_key:
        validate_unique_key(dataframe, unique_key, dataset_name=dataset_name)

    if non_null_key_columns:
        validate_non_null_columns(
            dataframe,
            non_null_key_columns,
            dataset_name=dataset_name,
        )
