from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class PipelinePaths:
    data_source_dir: Path
    models_repo_dir: Path
    platform_repo_dir: Path
    python_exe: Path
    consolidated_validations_path: Path


def resolve_from_root(monorepo_root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (monorepo_root / path).resolve()


def resolve_pipeline_paths(config: Mapping[str, Any], *, monorepo_root: Path) -> PipelinePaths:
    root = monorepo_root.resolve()
    return PipelinePaths(
        data_source_dir=resolve_from_root(root, config["data_source_dir"]),
        models_repo_dir=resolve_from_root(root, config.get("models_repo_dir", "ml_pipeline")),
        platform_repo_dir=resolve_from_root(root, config.get("platform_repo_dir", "platform")),
        python_exe=root / ".venv" / "Scripts" / "python.exe",
        consolidated_validations_path=(
            root / "data" / "processed" / "validaciones" / "validaciones_consolidado.parquet"
        ),
    )


def missing_workbook_patterns(raw_data_dir: Path, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if not any(raw_data_dir.glob(pattern))]
