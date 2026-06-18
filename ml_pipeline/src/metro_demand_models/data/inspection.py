from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class DatasetInspection:
    dataset_name: str
    path: str
    row_count: int
    column_count: int
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    duplicate_count: int | None
    duplicate_key: tuple[str, ...]
    date_ranges: dict[str, dict[str, str | None]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_dataframe(
    dataframe: pd.DataFrame,
    *,
    dataset_name: str,
    dataset_path: Path | str,
    duplicate_key: tuple[str, ...] = (),
    date_columns: tuple[str, ...] = (),
) -> DatasetInspection:
    date_ranges: dict[str, dict[str, str | None]] = {}
    for column in date_columns:
        if column not in dataframe.columns:
            continue

        series = pd.to_datetime(dataframe[column], errors="coerce")
        date_ranges[column] = {
            "min": None if pd.isna(series.min()) else str(series.min()),
            "max": None if pd.isna(series.max()) else str(series.max()),
        }

    duplicate_count: int | None = None
    if duplicate_key:
        duplicate_count = int(dataframe.duplicated(subset=list(duplicate_key)).sum())

    return DatasetInspection(
        dataset_name=dataset_name,
        path=str(Path(dataset_path)),
        row_count=int(len(dataframe)),
        column_count=int(len(dataframe.columns)),
        dtypes={column: str(dtype) for column, dtype in dataframe.dtypes.items()},
        null_counts={
            column: int(count)
            for column, count in dataframe.isna().sum().items()
            if int(count) > 0
        },
        duplicate_count=duplicate_count,
        duplicate_key=duplicate_key,
        date_ranges=date_ranges,
    )
