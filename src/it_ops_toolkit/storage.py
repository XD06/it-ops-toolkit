from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import (
    Asset,
    ErrorInfo,
    ProbeResult,
    ProbeStatus,
    Report,
    RiskLevel,
    Target,
    TaskRun,
    TaskStatus,
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    target_refs TEXT NOT NULL,
    result_refs TEXT NOT NULL,
    log_refs TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_runs_started_at
ON task_runs(started_at);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    ip TEXT NOT NULL,
    hostname TEXT,
    mac TEXT,
    vendor TEXT,
    os_hint TEXT,
    asset_type TEXT,
    open_ports TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_ip
ON assets(ip);

CREATE TABLE IF NOT EXISTS probe_results (
    id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    request_id TEXT,
    probe_type TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER,
    observations TEXT NOT NULL,
    error TEXT,
    evidence TEXT NOT NULL,
    PRIMARY KEY (id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_probe_results_task_id
ON probe_results(task_id);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    format TEXT NOT NULL,
    path TEXT NOT NULL,
    summary TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_source_task_id
ON reports(source_task_id);
"""


class TaskRecordNotFound(RuntimeError):
    pass


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def save_task_run(self, task: TaskRun) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO task_runs (
                    id,
                    task_type,
                    requested_by,
                    source,
                    status,
                    risk_level,
                    started_at,
                    ended_at,
                    target_refs,
                    result_refs,
                    log_refs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.task_type,
                    task.requested_by,
                    task.source,
                    task.status.value,
                    task.risk_level.value,
                    task.started_at.isoformat(),
                    task.ended_at.isoformat() if task.ended_at else None,
                    json.dumps(task.target_refs, ensure_ascii=False),
                    json.dumps(task.result_refs, ensure_ascii=False),
                    json.dumps(task.log_refs, ensure_ascii=False),
                ),
            )

    def list_task_runs(self, *, limit: int = 20) -> list[TaskRun]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def get_task_run(self, task_id: str) -> TaskRun:
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM task_runs WHERE id = ?",
                (task_id,),
            ).fetchone()

        if row is None:
            raise TaskRecordNotFound(f"task not found: {task_id}")
        return self._row_to_task(row)

    def save_asset(self, asset: Asset) -> None:
        self.ensure_schema()
        existing = self.get_asset_by_ip(asset.ip)
        first_seen = existing.first_seen if existing else asset.first_seen
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO assets (
                    id,
                    ip,
                    hostname,
                    mac,
                    vendor,
                    os_hint,
                    asset_type,
                    open_ports,
                    first_seen,
                    last_seen,
                    status,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.id,
                    asset.ip,
                    asset.hostname,
                    asset.mac,
                    asset.vendor,
                    asset.os_hint,
                    asset.asset_type,
                    json.dumps(asset.open_ports, ensure_ascii=False),
                    first_seen.isoformat(),
                    asset.last_seen.isoformat(),
                    asset.status,
                    asset.source,
                ),
            )

    def list_assets(self) -> list[Asset]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM assets
                ORDER BY ip ASC
                """
            ).fetchall()
        return [self._row_to_asset(row) for row in rows]

    def get_asset_by_ip(self, ip: str) -> Asset | None:
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE ip = ?",
                (ip,),
            ).fetchone()
        return self._row_to_asset(row) if row else None

    def save_probe_result(self, result: ProbeResult) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO probe_results (
                    id,
                    task_id,
                    request_id,
                    probe_type,
                    target,
                    status,
                    started_at,
                    ended_at,
                    duration_ms,
                    observations,
                    error,
                    evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.id,
                    result.task_id,
                    result.request_id,
                    result.probe_type,
                    result.target.model_dump_json(),
                    result.status.value,
                    result.started_at.isoformat(),
                    result.ended_at.isoformat() if result.ended_at else None,
                    result.duration_ms,
                    json.dumps(result.observations, ensure_ascii=False),
                    result.error.model_dump_json() if result.error else None,
                    json.dumps(result.evidence, ensure_ascii=False),
                ),
            )

    def list_probe_results_for_task(self, task_id: str) -> list[ProbeResult]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM probe_results
                WHERE task_id = ?
                ORDER BY started_at ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_probe_result(row) for row in rows]

    def save_report(self, report: Report) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO reports (
                    id,
                    source_task_id,
                    report_type,
                    title,
                    format,
                    path,
                    summary,
                    generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.source_task_id,
                    report.report_type,
                    report.title,
                    report.format,
                    report.path,
                    report.summary,
                    report.generated_at.isoformat(),
                ),
            )

    def _row_to_task(self, row: sqlite3.Row) -> TaskRun:
        values: dict[str, Any] = dict(row)
        return TaskRun(
            id=values["id"],
            task_type=values["task_type"],
            requested_by=values["requested_by"],
            source=values["source"],
            status=TaskStatus(values["status"]),
            risk_level=RiskLevel(values["risk_level"]),
            started_at=values["started_at"],
            ended_at=values["ended_at"],
            target_refs=json.loads(values["target_refs"]),
            result_refs=json.loads(values["result_refs"]),
            log_refs=json.loads(values["log_refs"]),
        )

    def _row_to_asset(self, row: sqlite3.Row) -> Asset:
        values: dict[str, Any] = dict(row)
        return Asset(
            id=values["id"],
            ip=values["ip"],
            hostname=values["hostname"],
            mac=values["mac"],
            vendor=values["vendor"],
            os_hint=values["os_hint"],
            asset_type=values["asset_type"],
            open_ports=json.loads(values["open_ports"]),
            first_seen=values["first_seen"],
            last_seen=values["last_seen"],
            status=values["status"],
            source=values["source"],
        )

    def _row_to_probe_result(self, row: sqlite3.Row) -> ProbeResult:
        values: dict[str, Any] = dict(row)
        error = ErrorInfo.model_validate_json(values["error"]) if values["error"] else None
        return ProbeResult(
            id=values["id"],
            request_id=values["request_id"],
            task_id=values["task_id"],
            probe_type=values["probe_type"],
            target=Target.model_validate_json(values["target"]),
            status=ProbeStatus(values["status"]),
            started_at=values["started_at"],
            ended_at=values["ended_at"],
            duration_ms=values["duration_ms"],
            observations=json.loads(values["observations"]),
            error=error,
            evidence=json.loads(values["evidence"]),
        )
