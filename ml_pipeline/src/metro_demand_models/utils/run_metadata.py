from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def file_sha256(path: str | Path) -> str | None:
    resolved = Path(path)
    if not resolved.exists() or not resolved.is_file():
        return None
    digest = hashlib.sha256()
    with resolved.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(project_root: str | Path) -> dict[str, str | None]:
    root = Path(project_root)
    return {
        "commit": _git(["rev-parse", "HEAD"], root),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "dirty": _git(["status", "--short"], root),
    }


def build_artifact_manifest(paths: dict[str, str]) -> dict[str, dict[str, Any]]:
    manifest: dict[str, dict[str, Any]] = {}
    for name, value in sorted(paths.items()):
        path = Path(value)
        manifest[name] = {
            "path": str(path),
            "exists": path.exists(),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        }
    return manifest


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def _git(args: list[str], root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
