from __future__ import annotations

import pandas as pd
import pytest

from metro_demand_models.data.io import discover_data_files, read_table
from metro_demand_models.data.validation import validate_required_columns


def test_read_table_supports_csv(tmp_path) -> None:
    csv_path = tmp_path / "sample.csv"
    expected_frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01 08:00:00", "2026-01-01 08:15:00"],
            "demand": [120, 140],
        }
    )
    expected_frame.to_csv(csv_path, index=False)

    loaded_frame = read_table(csv_path)

    assert list(loaded_frame.columns) == ["timestamp", "demand"]
    assert loaded_frame.shape == (2, 2)


def test_read_table_supports_excel(tmp_path) -> None:
    excel_path = tmp_path / "sample.xlsx"
    expected_frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01 08:00:00", "2026-01-01 08:15:00"],
            "demand": [120, 140],
        }
    )
    expected_frame.to_excel(excel_path, index=False)

    loaded_frame = read_table(excel_path)

    assert list(loaded_frame.columns) == ["timestamp", "demand"]
    assert loaded_frame.shape == (2, 2)


def test_discover_data_files_returns_supported_sources(tmp_path) -> None:
    csv_path = tmp_path / "sample.csv"
    parquet_path = tmp_path / "sample.parquet"
    excel_path = tmp_path / "sample.xlsx"
    tmp_path.joinpath("ignored.txt").write_text("ignore me", encoding="utf-8")

    pd.DataFrame({"demand": [1]}).to_csv(csv_path, index=False)
    pd.DataFrame({"demand": [1]}).to_parquet(parquet_path, index=False)
    pd.DataFrame({"demand": [1]}).to_excel(excel_path, index=False)

    discovered_files = discover_data_files(tmp_path)

    assert discovered_files == sorted(
        [csv_path.resolve(), excel_path.resolve(), parquet_path.resolve()],
        key=str,
    )


def test_validate_required_columns_raises_for_missing_columns() -> None:
    dataframe = pd.DataFrame({"timestamp": ["2026-01-01 08:00:00"], "demand": [120]})

    with pytest.raises(ValueError, match="Missing required columns"):
        validate_required_columns(dataframe, ["timestamp", "demand", "station"])
