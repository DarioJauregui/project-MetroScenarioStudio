from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PipelineRunSummary:
    def __init__(self, monorepo_root: Path, *, output_name: str = "pipeline_run_summary.json") -> None:
        self.monorepo_root = Path(monorepo_root)
        self.output_path = self.monorepo_root / "ml_pipeline" / "artifacts" / "monitoring" / output_name
        self.started_at = _now()
        self.finished_at: str | None = None
        self.steps: list[dict[str, Any]] = []
        self._active_steps: dict[str, dict[str, Any]] = {}

    def start_step(self, name: str, *, critical: bool = True, metadata: dict[str, Any] | None = None) -> None:
        step = {
            "name": name,
            "critical": critical,
            "status": "running",
            "started_at": _now(),
            "finished_at": None,
            "duration_seconds": None,
            "message": None,
            "artifacts": {},
            "metadata": metadata or {},
        }
        self.steps.append(step)
        self._active_steps[name] = step

    def finish_step(
        self,
        name: str,
        *,
        status: str,
        critical: bool | None = None,
        message: str | None = None,
        artifacts: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        step = self._active_steps.pop(name, None)
        if step is None:
            self.start_step(name, critical=True if critical is None else critical)
            step = self._active_steps.pop(name)
        finished_at = _now()
        step["status"] = status
        if critical is not None:
            step["critical"] = critical
        step["finished_at"] = finished_at
        step["duration_seconds"] = _duration_seconds(str(step["started_at"]), finished_at)
        step["message"] = message
        step["artifacts"] = artifacts or {}
        if metadata:
            step["metadata"] = {**step.get("metadata", {}), **metadata}

    def write(self) -> Path:
        self.finished_at = _now()
        payload = {
            "schema_version": 1,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "global_status": self.global_status(),
            "steps": self.steps,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return self.output_path

    def global_status(self) -> str:
        if any(step["status"] == "failed" and step.get("critical", True) for step in self.steps):
            return "failed"
        if any(step["status"] in {"failed", "skipped"} for step in self.steps):
            return "warning"
        if any(step["status"] == "running" for step in self.steps):
            return "running"
        return "success"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _duration_seconds(start: str, end: str) -> float:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 6)
