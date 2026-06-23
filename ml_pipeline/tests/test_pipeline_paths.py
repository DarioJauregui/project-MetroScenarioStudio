from __future__ import annotations

import sys
from pathlib import Path


MONOREPO_ROOT = Path(__file__).resolve().parents[2]
if str(MONOREPO_ROOT) not in sys.path:
    sys.path.insert(0, str(MONOREPO_ROOT))


def test_pipeline_path_config_resolves_relative_repos_from_monorepo_root() -> None:
    from pipelines.path_resolution import resolve_pipeline_paths

    resolved = resolve_pipeline_paths(
        {
            "data_source_dir": r"D:\ruta\local\validaciones",
            "models_repo_dir": "ml_pipeline",
            "platform_repo_dir": "platform",
        },
        monorepo_root=MONOREPO_ROOT,
    )

    assert resolved.data_source_dir == Path(r"D:\ruta\local\validaciones")
    assert resolved.models_repo_dir == MONOREPO_ROOT / "ml_pipeline"
    assert resolved.platform_repo_dir == MONOREPO_ROOT / "platform"
    assert resolved.python_exe == MONOREPO_ROOT / ".venv" / "Scripts" / "python.exe"
    assert resolved.consolidated_validations_path == (
        MONOREPO_ROOT / "data" / "processed" / "validaciones" / "validaciones_consolidado.parquet"
    )


def test_missing_workbook_patterns_reports_only_absent_patterns(tmp_path) -> None:
    from pipelines.path_resolution import missing_workbook_patterns

    (tmp_path / "Calendario_Eventos.xlsx").write_text("placeholder", encoding="utf-8")

    assert missing_workbook_patterns(
        tmp_path,
        ("Servicios Hist*.xlsx", "Calendario_Eventos.xlsx"),
    ) == ["Servicios Hist*.xlsx"]
