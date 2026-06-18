from __future__ import annotations

import json
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


Settings = dict[str, Any]


def find_project_root(start_path: Path | None = None) -> Path:
    current_path = (start_path or Path(__file__).resolve()).resolve()
    current_dir = current_path if current_path.is_dir() else current_path.parent

    for candidate in [current_dir, *current_dir.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate

    raise FileNotFoundError(f"Could not find project root from '{current_path}'.")


def deep_merge_dicts(base: Settings, override: Settings) -> Settings:
    merged = deepcopy(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dicts(merged[key], value)
            continue

        merged[key] = deepcopy(value)

    return merged


def load_toml_file(path: Path) -> Settings:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: '{path}'.")

    with path.open("rb") as file_handle:
        return tomllib.load(file_handle)


def resolve_path(project_root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (project_root / path).resolve()


def load_settings(project_root: Path | None = None) -> Settings:
    root = find_project_root(project_root)
    base_config_path = root / "conf" / "base" / "config.toml"
    local_config_path = root / "conf" / "local" / "config.toml"

    settings = load_toml_file(base_config_path)
    loaded_files = [base_config_path]

    if local_config_path.exists():
        local_settings = load_toml_file(local_config_path)
        settings = deep_merge_dicts(settings, local_settings)
        loaded_files.append(local_config_path)

    settings["runtime"] = {
        "project_root": str(root),
        "loaded_config_files": [str(path) for path in loaded_files],
    }
    settings["resolved_paths"] = {
        name: str(resolve_path(root, raw_path)) for name, raw_path in settings.get("paths", {}).items()
    }
    return settings


def get_path(settings: Settings, name: str) -> Path:
    try:
        return Path(settings["resolved_paths"][name])
    except KeyError as error:
        raise KeyError(f"Missing path configuration for '{name}'.") from error


def dump_settings(settings: Settings) -> str:
    return json.dumps(settings, indent=2, sort_keys=True)
