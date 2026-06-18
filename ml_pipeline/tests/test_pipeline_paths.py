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
            "data_source_dir": r"M:\AOPJA\Informes\1_Inf_diarios\xx_Automaticos_EnPruebas",
            "models_repo_dir": "ml_pipeline",
            "platform_repo_dir": "platform",
        },
        monorepo_root=MONOREPO_ROOT,
    )

    assert resolved.data_source_dir == Path(r"M:\AOPJA\Informes\1_Inf_diarios\xx_Automaticos_EnPruebas")
    assert resolved.models_repo_dir == MONOREPO_ROOT / "ml_pipeline"
    assert resolved.platform_repo_dir == MONOREPO_ROOT / "platform"
    assert resolved.python_exe == MONOREPO_ROOT / ".venv" / "Scripts" / "python.exe"
    assert resolved.consolidated_validations_path == (
        MONOREPO_ROOT / "data" / "processed" / "validaciones" / "validaciones_consolidado.parquet"
    )
