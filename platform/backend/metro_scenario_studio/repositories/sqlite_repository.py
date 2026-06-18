from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from metro_scenario_studio.domain.schemas import (
    AuditEvent,
    ExecutionResult,
    ExternalDataSnapshot,
    ScenarioExecution,
)

if TYPE_CHECKING:
    from pathlib import Path


class SQLiteRepository:
    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def save_execution(self, execution: ScenarioExecution) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scenario_executions (
                    id, status, real_data_status, origin_type, parent_execution_id,
                    range_start, range_end, author, comment, created_at, updated_at,
                    executed_at, model_name, model_variant, dataset_version, warnings_json,
                    execution_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    real_data_status=excluded.real_data_status,
                    origin_type=excluded.origin_type,
                    parent_execution_id=excluded.parent_execution_id,
                    range_start=excluded.range_start,
                    range_end=excluded.range_end,
                    author=excluded.author,
                    comment=excluded.comment,
                    updated_at=excluded.updated_at,
                    executed_at=excluded.executed_at,
                    model_name=excluded.model_name,
                    model_variant=excluded.model_variant,
                    dataset_version=excluded.dataset_version,
                    warnings_json=excluded.warnings_json,
                    execution_json=excluded.execution_json
                """,
                (
                    execution.id,
                    execution.status.value,
                    execution.real_data_status,
                    execution.origin_type.value,
                    execution.parent_execution_id,
                    execution.range_start.isoformat(),
                    execution.range_end.isoformat(),
                    execution.author,
                    execution.comment,
                    execution.created_at.isoformat(),
                    execution.updated_at.isoformat(),
                    execution.executed_at.isoformat() if execution.executed_at else None,
                    execution.model_name,
                    execution.model_variant,
                    execution.dataset_version,
                    json.dumps(execution.warnings, ensure_ascii=False),
                    json.dumps(execution.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            connection.commit()

    def save_result(self, result: ExecutionResult) -> None:
        self.save_execution(result.execution)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO execution_results (execution_id, result_json)
                VALUES (?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET result_json=excluded.result_json
                """,
                (
                    result.execution.id,
                    json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            connection.execute("DELETE FROM prediction_rows WHERE execution_id = ?", (result.execution.id,))
            connection.execute("DELETE FROM scenario_aggregates WHERE execution_id = ?", (result.execution.id,))
            connection.execute("DELETE FROM explanation_items WHERE execution_id = ?", (result.execution.id,))
            connection.executemany(
                """
                INSERT INTO prediction_rows (
                    execution_id, target_date, linea, estacion, series_id, station_abbrev,
                    network_order, y_pred, y_real, model_variant, horizon_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.execution.id,
                        row.target_date.isoformat(),
                        row.linea,
                        row.estacion,
                        row.series_id,
                        row.station_abbrev,
                        row.network_order,
                        row.y_pred,
                        row.y_real,
                        row.model_variant,
                        row.horizon_days,
                    )
                    for row in result.prediction_rows
                ],
            )
            connection.executemany(
                "INSERT INTO scenario_aggregates (execution_id, aggregate_json) VALUES (?, ?)",
                [
                    (
                        result.execution.id,
                        json.dumps(row.model_dump(mode="json"), ensure_ascii=False),
                    )
                    for row in result.aggregates
                ],
            )
            connection.executemany(
                "INSERT INTO explanation_items (execution_id, explanation_json) VALUES (?, ?)",
                [
                    (
                        result.execution.id,
                        json.dumps(row.model_dump(mode="json"), ensure_ascii=False),
                    )
                    for row in result.explanations
                ],
            )
            connection.executemany(
                "INSERT INTO audit_events (execution_id, audit_json) VALUES (?, ?)",
                [
                    (
                        result.execution.id,
                        json.dumps(row.model_dump(mode="json"), ensure_ascii=False),
                    )
                    for row in result.audit_events
                ],
            )
            connection.commit()

    def save_external_snapshot(
        self,
        *,
        execution_id: str,
        snapshot: ExternalDataSnapshot,
    ) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM external_snapshots WHERE execution_id = ?", (execution_id,))
            connection.execute(
                "INSERT INTO external_snapshots (execution_id, snapshot_json) VALUES (?, ?)",
                (
                    execution_id,
                    json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            connection.commit()

    def save_excel_artifact(
        self,
        *,
        execution_id: str,
        artifact_type: str,
        path: Path,
        checksum: str | None,
        schema_version: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_artifacts (
                    execution_id, artifact_type, path, checksum, schema_version
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (execution_id, artifact_type, str(path), checksum, schema_version),
            )
            connection.commit()

    def add_audit_event(self, event: AuditEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events (execution_id, audit_json) VALUES (?, ?)",
                (
                    event.execution_id,
                    json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            connection.commit()

    def save_model_registry_snapshot(self, snapshot: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO model_registry_snapshots (snapshot_json, created_at) VALUES (?, ?)",
                (
                    json.dumps(snapshot, ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()

    def get_execution(self, execution_id: str) -> ScenarioExecution:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT execution_json FROM scenario_executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Execution '{execution_id}' not found.")
        return ScenarioExecution.model_validate(json.loads(row["execution_json"]))

    def execution_exists(self, execution_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM scenario_executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        return row is not None

    def get_result(self, execution_id: str) -> ExecutionResult:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM execution_results WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Result for execution '{execution_id}' not found.")
        return ExecutionResult.model_validate(json.loads(row["result_json"]))

    def get_audit_events(self, execution_id: str) -> list[AuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT audit_json FROM audit_events WHERE execution_id = ? ORDER BY rowid",
                (execution_id,),
            ).fetchall()
        return [AuditEvent.model_validate(json.loads(row["audit_json"])) for row in rows]

    def get_excel_artifacts(self, execution_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT execution_id, artifact_type, path, checksum, schema_version
                FROM excel_artifacts
                WHERE execution_id = ?
                ORDER BY rowid
                """,
                (execution_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_external_snapshot(self, execution_id: str) -> ExternalDataSnapshot:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM external_snapshots WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"External snapshot for execution '{execution_id}' not found.")
        return ExternalDataSnapshot.model_validate(json.loads(row["snapshot_json"]))

    def list_executions(self) -> list[ScenarioExecution]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT execution_json FROM scenario_executions ORDER BY created_at DESC"
            ).fetchall()
        return [ScenarioExecution.model_validate(json.loads(row["execution_json"])) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path, check_same_thread=False, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scenario_executions (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    real_data_status TEXT NOT NULL,
                    origin_type TEXT NOT NULL,
                    parent_execution_id TEXT,
                    range_start TEXT NOT NULL,
                    range_end TEXT NOT NULL,
                    author TEXT,
                    comment TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    executed_at TEXT,
                    model_name TEXT NOT NULL,
                    model_variant TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    execution_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scenario_inputs (
                    execution_id TEXT PRIMARY KEY,
                    input_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS external_snapshots (
                    execution_id TEXT,
                    snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prediction_rows (
                    execution_id TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    linea TEXT NOT NULL,
                    estacion TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    station_abbrev TEXT NOT NULL,
                    network_order INTEGER NOT NULL,
                    y_pred REAL NOT NULL,
                    y_real REAL,
                    model_variant TEXT NOT NULL,
                    horizon_days INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scenario_aggregates (
                    execution_id TEXT,
                    aggregate_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS explanation_items (
                    execution_id TEXT,
                    explanation_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    execution_id TEXT,
                    audit_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS excel_artifacts (
                    execution_id TEXT,
                    artifact_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    checksum TEXT,
                    schema_version TEXT
                );
                CREATE TABLE IF NOT EXISTS model_registry_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS execution_results (
                    execution_id TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL
                );
                """
            )
            connection.commit()
