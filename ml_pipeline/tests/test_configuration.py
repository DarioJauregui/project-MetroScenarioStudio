from __future__ import annotations

from pathlib import Path

from metro_demand_models.configuration import deep_merge_dicts, get_path, load_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_settings_reads_base_configuration() -> None:
    settings = load_settings(PROJECT_ROOT)

    assert settings["project"]["name"] == "metro-demand-models"
    assert settings["project"]["python_version"] == "3.12"
    assert "raw_data_dir" in settings["paths"]
    assert get_path(settings, "raw_data_dir").is_absolute()


def test_base_configuration_resolves_shared_data_from_monorepo_root() -> None:
    settings = load_settings(PROJECT_ROOT)

    monorepo_root = PROJECT_ROOT.parent
    assert get_path(settings, "data_dir") == monorepo_root / "data"
    assert get_path(settings, "raw_data_dir") == monorepo_root / "data" / "raw"
    assert get_path(settings, "processed_validations_file") == (
        monorepo_root / "data" / "processed" / "validaciones" / "validaciones_consolidado.parquet"
    )
    assert get_path(settings, "artifacts_dir") == PROJECT_ROOT / "artifacts"


def test_deep_merge_dicts_preserves_nested_values() -> None:
    base = {"paths": {"raw_data_dir": "data/raw", "reports_dir": "artifacts/reports"}}
    override = {"paths": {"reports_dir": "custom/reports"}}

    merged = deep_merge_dicts(base, override)

    assert merged["paths"]["raw_data_dir"] == "data/raw"
    assert merged["paths"]["reports_dir"] == "custom/reports"
