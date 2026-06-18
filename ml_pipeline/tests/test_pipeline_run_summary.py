from __future__ import annotations

import json
from pathlib import Path

from pipelines.run_summary import PipelineRunSummary


def test_pipeline_run_summary_records_steps_and_global_status(tmp_path: Path) -> None:
    summary = PipelineRunSummary(tmp_path)
    summary.start_step("ingest")
    summary.finish_step("ingest", status="success", artifacts={"weather": "weather.parquet"})
    summary.start_step("optional_ops")
    summary.finish_step("optional_ops", status="failed", critical=False, message="missing workbook")

    path = summary.write()
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["global_status"] == "warning"
    assert payload["steps"][0]["name"] == "ingest"
    assert payload["steps"][0]["artifacts"]["weather"] == "weather.parquet"
    assert payload["steps"][1]["status"] == "failed"
    assert payload["steps"][1]["critical"] is False
