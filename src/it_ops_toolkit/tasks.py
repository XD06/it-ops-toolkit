from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .models import RiskLevel, TaskRun, TaskStatus
from .storage import SQLiteStore


def new_task_run(
    *,
    task_type: str,
    requested_by: str = "local",
    status: TaskStatus = TaskStatus.running,
    risk_level: RiskLevel = RiskLevel.read_only,
) -> TaskRun:
    return TaskRun(
        id=f"task-{uuid4().hex[:12]}",
        task_type=task_type,
        requested_by=requested_by,
        source="cli",
        status=status,
        risk_level=risk_level,
        started_at=datetime.now(UTC),
    )


def list_tasks(store: SQLiteStore, *, limit: int = 20) -> list[TaskRun]:
    return store.list_task_runs(limit=limit)


def get_task(store: SQLiteStore, task_id: str) -> TaskRun:
    return store.get_task_run(task_id)


def finish_task_run(task: TaskRun, *, status: TaskStatus) -> TaskRun:
    return task.model_copy(
        update={
            "status": status,
            "ended_at": datetime.now(UTC),
        }
    )
