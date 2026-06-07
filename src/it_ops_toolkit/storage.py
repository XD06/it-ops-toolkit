from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import RiskLevel, TaskRun, TaskStatus


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

