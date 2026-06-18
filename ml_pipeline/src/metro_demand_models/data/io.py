from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_SUFFIXES = {
    ".parquet": "parquet",
    ".csv": "csv",
    ".xlsx": "excel",
    ".xlsm": "excel",
}


def discover_data_files(
    directory: Path | str,
    patterns: Iterable[str] | None = None,
) -> list[Path]:
    source_directory = Path(directory)
    if not source_directory.exists():
        raise FileNotFoundError(f"Data directory not found: '{source_directory}'.")

    search_patterns = list(patterns or ("*.parquet", "*.csv", "*.xlsx", "*.xlsm"))
    discovered_files = {
        file_path.resolve()
        for pattern in search_patterns
        for file_path in source_directory.rglob(pattern)
        if file_path.is_file()
    }
    return sorted(discovered_files, key=lambda path: str(path))


def read_table(file_path: Path | str, **kwargs: Any) -> pd.DataFrame:
    dataset_path = Path(file_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: '{dataset_path}'.")

    suffix = dataset_path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(dataset_path, **kwargs)

    if suffix == ".csv":
        return pd.read_csv(dataset_path, **kwargs)

    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(dataset_path, **kwargs)

    supported_extensions = ", ".join(sorted(SUPPORTED_SUFFIXES))
    raise ValueError(
        f"Unsupported dataset format for '{dataset_path}'. Supported formats: "
        f"{supported_extensions}."
    )
