from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    Asset,
    ErrorInfo,
    Finding,
    LocalInterface,
    LocalSnapshot,
    NotificationLog,
    ProbeResult,
    ProbeStatus,
    Report,
    RiskLevel,
    ScheduledTask,
    ScheduledTaskStatus,
    Target,
    TaskRun,
    TaskStatus,
    AICallLog,
    StepStatus,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowStepExecution,
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
    log_refs TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '{}'
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
    source TEXT NOT NULL,
    owner TEXT,
    description TEXT,
    tags TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_assets_ip
ON assets(ip);

CREATE TABLE IF NOT EXISTS local_snapshots (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    hostname TEXT NOT NULL,
    fqdn TEXT,
    username TEXT,
    os_name TEXT NOT NULL,
    platform TEXT NOT NULL,
    interfaces TEXT NOT NULL,
    default_routes TEXT NOT NULL,
    dns_servers TEXT NOT NULL,
    proxy TEXT NOT NULL,
    observations TEXT NOT NULL,
    raw TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_local_snapshots_task_id
ON local_snapshots(task_id);

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

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence_refs TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    requires_human_review INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_task_id
ON findings(task_id);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    profile TEXT NOT NULL,
    cron TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    alert_on TEXT NOT NULL DEFAULT '[]',
    last_run TEXT,
    next_run TEXT,
    last_status TEXT,
    last_task_id TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS alert_events (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    target TEXT NOT NULL,
    probe_type TEXT NOT NULL,
    metric TEXT NOT NULL,
    value TEXT NOT NULL,
    threshold TEXT NOT NULL,
    task_id TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    status TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_at TEXT,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_events_status
ON alert_events(status);

CREATE INDEX IF NOT EXISTS idx_alert_events_rule_target
ON alert_events(rule_id, target, status);

CREATE TABLE IF NOT EXISTS notification_logs (
    id TEXT PRIMARY KEY,
    alert_event_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    sent_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_notification_logs_alert_event_id
ON notification_logs(alert_event_id);

CREATE TABLE IF NOT EXISTS ai_call_logs (
id TEXT PRIMARY KEY,
task_id TEXT NOT NULL,
backend TEXT NOT NULL,
success INTEGER NOT NULL,
duration_ms INTEGER NOT NULL DEFAULT 0,
error TEXT,
called_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_call_logs_task_id
ON ai_call_logs(task_id);

CREATE TABLE IF NOT EXISTS workflow_executions (
    id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    status TEXT NOT NULL,
    trigger TEXT NOT NULL,
    steps TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    context TEXT NOT NULL,
    result_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_executions_name
ON workflow_executions(workflow_name);

CREATE INDEX IF NOT EXISTS idx_workflow_executions_status
ON workflow_executions(status);
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
        self._ensure_task_runs_summary_column()
        self._ensure_asset_notes_columns()

    def _ensure_task_runs_summary_column(self) -> None:
        with self.connect() as connection:
            columns = connection.execute("PRAGMA table_info(task_runs)").fetchall()
            if any(column[1] == "summary" for column in columns):
                return
            connection.execute(
                "ALTER TABLE task_runs ADD COLUMN summary TEXT NOT NULL DEFAULT '{}'"
            )

    def _ensure_asset_notes_columns(self) -> None:
        with self.connect() as connection:
            columns = connection.execute("PRAGMA table_info(assets)").fetchall()
            column_names = {column[1] for column in columns}
            if "owner" not in column_names:
                connection.execute("ALTER TABLE assets ADD COLUMN owner TEXT")
            if "description" not in column_names:
                connection.execute("ALTER TABLE assets ADD COLUMN description TEXT")
            if "tags" not in column_names:
                connection.execute(
                    "ALTER TABLE assets ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"
                )

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
                    log_refs,
                    summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(task.summary, ensure_ascii=False),
                ),
            )

    def list_task_runs(self, *, limit: int = 20) -> list[TaskRun]:
        self.ensure_schema()
        self._ensure_task_runs_summary_column()
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
        self._ensure_task_runs_summary_column()
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
        owner = asset.owner if asset.owner is not None else existing.owner if existing else None
        description = (
            asset.description
            if asset.description is not None
            else existing.description if existing else None
        )
        tags = asset.tags if asset.tags else existing.tags if existing else []
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
                    source,
                    owner,
                    description,
                    tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    owner,
                    description,
                    json.dumps(tags, ensure_ascii=False),
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

    def save_local_snapshot(self, snapshot: LocalSnapshot) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO local_snapshots (
                    id,
                    task_id,
                    collected_at,
                    hostname,
                    fqdn,
                    username,
                    os_name,
                    platform,
                    interfaces,
                    default_routes,
                    dns_servers,
                    proxy,
                    observations,
                    raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.task_id,
                    snapshot.collected_at.isoformat(),
                    snapshot.hostname,
                    snapshot.fqdn,
                    snapshot.username,
                    snapshot.os_name,
                    snapshot.platform,
                    json.dumps(
                        [interface.model_dump(mode="json") for interface in snapshot.interfaces],
                        ensure_ascii=False,
                    ),
                    json.dumps(snapshot.default_routes, ensure_ascii=False),
                    json.dumps(snapshot.dns_servers, ensure_ascii=False),
                    json.dumps(snapshot.proxy, ensure_ascii=False),
                    json.dumps(snapshot.observations, ensure_ascii=False),
                    json.dumps(snapshot.raw, ensure_ascii=False),
                ),
            )

    def list_local_snapshots_for_task(self, task_id: str) -> list[LocalSnapshot]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM local_snapshots
                WHERE task_id = ?
                ORDER BY collected_at ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_local_snapshot(row) for row in rows]

    def list_all_local_snapshots(self) -> list[LocalSnapshot]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM local_snapshots
                ORDER BY collected_at ASC
                """
            ).fetchall()
        return [self._row_to_local_snapshot(row) for row in rows]

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

    def list_all_probe_results(self) -> list[ProbeResult]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM probe_results
                ORDER BY started_at ASC
                """
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

    def list_reports(self, *, limit: int = 50) -> list[Report]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM reports
                ORDER BY generated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_report(row) for row in rows]

    def get_report(self, report_id: str) -> Report | None:
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        return self._row_to_report(row) if row else None

    def _row_to_report(self, row: sqlite3.Row) -> Report:
        values: dict[str, Any] = dict(row)
        return Report(
            id=values["id"],
            source_task_id=values["source_task_id"],
            report_type=values["report_type"],
            title=values["title"],
            format=values["format"],
            path=values["path"],
            summary=values["summary"],
            generated_at=values["generated_at"],
        )

    def save_finding(self, finding: Finding) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO findings (
                    id,
                    task_id,
                    category,
                    severity,
                    title,
                    description,
                    evidence_refs,
                    recommendation,
                    requires_human_review
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.id,
                    finding.task_id,
                    finding.category,
                    finding.severity.value,
                    finding.title,
                    finding.description,
                    json.dumps(finding.evidence_refs, ensure_ascii=False),
                    finding.recommendation,
                    int(finding.requires_human_review),
                ),
            )

    def list_findings_for_task(self, task_id: str) -> list[Finding]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM findings
                WHERE task_id = ?
                ORDER BY severity DESC, id ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_finding(row) for row in rows]

    def list_all_findings(self) -> list[Finding]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM findings
                ORDER BY task_id ASC, id ASC
                """
            ).fetchall()
        return [self._row_to_finding(row) for row in rows]

    def list_findings(self, task_id: str) -> list[Finding]:
        """list_findings_for_task 的别名，供 AI 模块调用。"""
        return self.list_findings_for_task(task_id)

    def list_findings_for_results(self, result_ids: list[str]) -> list[Finding]:
        """根据探测结果 ID 列表查找关联的 findings。"""
        self.ensure_schema()
        if not result_ids:
            return []

        # findings 通过 evidence_refs 关联 probe_result ID
        # evidence_refs 是 JSON 数组，用 LIKE 查询
        placeholders = ",".join("?" for _ in result_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM findings
                WHERE id IN (
                    SELECT f.id FROM findings f
                    WHERE {' OR '.join(f'f.evidence_refs LIKE ?' for _ in result_ids)}
                )
                ORDER BY severity DESC, id ASC
                """,
                [f'%"{rid}"%' for rid in result_ids],
            ).fetchall()
        return [self._row_to_finding(row) for row in rows]

    def save_ai_call_log(self, log: AICallLog) -> None:
        """保存 AI 调用审计日志。"""
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_call_logs (
                    id, task_id, backend, success, duration_ms, error, called_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.id,
                    log.task_id,
                    log.backend,
                    int(log.success),
                    log.duration_ms,
                    log.error,
                    log.called_at.isoformat(),
                ),
            )

    def list_ai_call_logs(self, *, task_id: str | None = None, limit: int = 100) -> list[AICallLog]:
        """查询 AI 调用审计日志。"""
        self.ensure_schema()
        with self.connect() as connection:
            if task_id:
                rows = connection.execute(
                    "SELECT * FROM ai_call_logs WHERE task_id = ? ORDER BY called_at DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM ai_call_logs ORDER BY called_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_ai_call_log(row) for row in rows]

    def _row_to_ai_call_log(self, row: sqlite3.Row) -> AICallLog:
        values: dict[str, Any] = dict(row)
        return AICallLog(
            id=values["id"],
            task_id=values["task_id"],
            backend=values["backend"],
            success=bool(values["success"]),
            duration_ms=values["duration_ms"],
            error=values.get("error"),
            called_at=datetime.fromisoformat(values["called_at"]),
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
            summary=json.loads(values["summary"]) if values.get("summary") else {},
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
            owner=values.get("owner"),
            description=values.get("description"),
            tags=json.loads(values["tags"]) if values.get("tags") else [],
        )

    def _row_to_local_snapshot(self, row: sqlite3.Row) -> LocalSnapshot:
        values: dict[str, Any] = dict(row)
        return LocalSnapshot(
            id=values["id"],
            task_id=values["task_id"],
            collected_at=values["collected_at"],
            hostname=values["hostname"],
            fqdn=values["fqdn"],
            username=values["username"],
            os_name=values["os_name"],
            platform=values["platform"],
            interfaces=[
                LocalInterface.model_validate(interface)
                for interface in json.loads(values["interfaces"])
            ],
            default_routes=json.loads(values["default_routes"]),
            dns_servers=json.loads(values["dns_servers"]),
            proxy=json.loads(values["proxy"]),
            observations=json.loads(values["observations"]),
            raw=json.loads(values["raw"]),
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

    def _row_to_finding(self, row: sqlite3.Row) -> Finding:
        values: dict[str, Any] = dict(row)
        return Finding(
            id=values["id"],
            task_id=values["task_id"],
            category=values["category"],
            severity=values["severity"],
            title=values["title"],
            description=values["description"],
            evidence_refs=json.loads(values["evidence_refs"]),
            recommendation=values["recommendation"],
            requires_human_review=bool(values["requires_human_review"]),
        )

    # -----------------------------------------------------------------------
    # Phase 5：定时任务状态持久化
    # -----------------------------------------------------------------------

    def save_scheduled_task(self, task: ScheduledTask) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO scheduled_tasks (
                    id, name, task_type, profile, cron, enabled,
                    alert_on, last_run, next_run, last_status,
                    last_task_id, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.name,
                    task.task_type,
                    task.profile,
                    task.cron,
                    int(task.enabled),
                    json.dumps([s.value for s in task.alert_on], ensure_ascii=False),
                    task.last_run.isoformat() if task.last_run else None,
                    task.next_run.isoformat() if task.next_run else None,
                    task.last_status.value if task.last_status else None,
                    task.last_task_id,
                    task.last_error,
                ),
            )

    def list_scheduled_tasks(self) -> list[ScheduledTask]:
        self.ensure_schema()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scheduled_tasks ORDER BY name ASC"
            ).fetchall()
        return [self._row_to_scheduled_task(row) for row in rows]

    def get_scheduled_task(self, task_id: str) -> ScheduledTask | None:
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row_to_scheduled_task(row) if row else None

    def delete_scheduled_task(self, task_id: str) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM scheduled_tasks WHERE id = ?", (task_id,)
            )

    def _row_to_scheduled_task(self, row: sqlite3.Row) -> ScheduledTask:
        values: dict[str, Any] = dict(row)
        alert_on_raw = json.loads(values.get("alert_on") or "[]")
        alert_on = [AlertSeverity(s) for s in alert_on_raw]
        last_status_raw = values.get("last_status")
        last_status = ScheduledTaskStatus(last_status_raw) if last_status_raw else None
        return ScheduledTask(
            id=values["id"],
            name=values["name"],
            task_type=values["task_type"],
            profile=values["profile"],
            cron=values["cron"],
            enabled=bool(values["enabled"]),
            alert_on=alert_on,
            last_run=values["last_run"],
            next_run=values["next_run"],
            last_status=last_status,
            last_task_id=values.get("last_task_id"),
            last_error=values.get("last_error"),
        )

    # -----------------------------------------------------------------------
    # Phase 5：告警事件持久化
    # -----------------------------------------------------------------------

    def save_alert_event(self, event: AlertEvent) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO alert_events (
                    id, rule_id, rule_name, severity, target,
                    probe_type, metric, value, threshold, task_id,
                    triggered_at, status, acknowledged, acknowledged_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.rule_id,
                    event.rule_name,
                    event.severity.value,
                    event.target,
                    event.probe_type,
                    event.metric,
                    event.value,
                    event.threshold,
                    event.task_id,
                    event.triggered_at.isoformat(),
                    event.status.value,
                    int(event.acknowledged),
                    event.acknowledged_at.isoformat() if event.acknowledged_at else None,
                    event.resolved_at.isoformat() if event.resolved_at else None,
                ),
            )

    def list_alert_events(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[AlertEvent]:
        self.ensure_schema()
        with self.connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM alert_events WHERE status = ? ORDER BY triggered_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM alert_events ORDER BY triggered_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_alert_event(row) for row in rows]

    def get_alert_event(self, event_id: str) -> AlertEvent | None:
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM alert_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._row_to_alert_event(row) if row else None

    def find_active_alert(
        self, rule_id: str, target: str
    ) -> AlertEvent | None:
        """查找同一规则 + 同一目标的活跃告警（用于冷却降噪）。"""
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM alert_events
                WHERE rule_id = ? AND target = ? AND status = 'active'
                ORDER BY triggered_at DESC LIMIT 1
                """,
                (rule_id, target),
            ).fetchone()
        return self._row_to_alert_event(row) if row else None

    def _row_to_alert_event(self, row: sqlite3.Row) -> AlertEvent:
        values: dict[str, Any] = dict(row)
        return AlertEvent(
            id=values["id"],
            rule_id=values["rule_id"],
            rule_name=values["rule_name"],
            severity=AlertSeverity(values["severity"]),
            target=values["target"],
            probe_type=values["probe_type"],
            metric=values["metric"],
            value=values["value"],
            threshold=values["threshold"],
            task_id=values["task_id"],
            triggered_at=values["triggered_at"],
            status=AlertStatus(values["status"]),
            acknowledged=bool(values["acknowledged"]),
            acknowledged_at=values.get("acknowledged_at"),
            resolved_at=values.get("resolved_at"),
        )

    # -----------------------------------------------------------------------
    # Phase 5：通知发送记录持久化
    # -----------------------------------------------------------------------

    def save_notification_log(self, log: NotificationLog) -> None:
        self.ensure_schema()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO notification_logs (
                    id, alert_event_id, channel, success, error, sent_at, retry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.id,
                    log.alert_event_id,
                    log.channel,
                    int(log.success),
                    log.error,
                    log.sent_at.isoformat(),
                    log.retry_count,
                ),
            )

    def list_notification_logs(
        self, *, alert_event_id: str | None = None, limit: int = 100
    ) -> list[NotificationLog]:
        self.ensure_schema()
        with self.connect() as connection:
            if alert_event_id:
                rows = connection.execute(
                    "SELECT * FROM notification_logs WHERE alert_event_id = ? ORDER BY sent_at DESC LIMIT ?",
                    (alert_event_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM notification_logs ORDER BY sent_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_notification_log(row) for row in rows]

    def _row_to_notification_log(self, row: sqlite3.Row) -> NotificationLog:
        values: dict[str, Any] = dict(row)
        return NotificationLog(
            id=values["id"],
            alert_event_id=values["alert_event_id"],
            channel=values["channel"],
            success=bool(values["success"]),
            error=values.get("error"),
            sent_at=values["sent_at"],
            retry_count=values["retry_count"],
        )

    # -----------------------------------------------------------------------
    # Phase 6：历史趋势查询与聚合
    # -----------------------------------------------------------------------

    def list_probe_results_between(
        self,
        *,
        start: str,
        end: str,
        probe_type: str | None = None,
        target: str | None = None,
        limit: int = 1000,
    ) -> list[ProbeResult]:
        """查询指定时间范围内的探测结果。

        Args:
            start: 起始时间 ISO 格式字符串。
            end: 结束时间 ISO 格式字符串。
            probe_type: 可选，按探针类型筛选。
            target: 可选，按目标筛选（IP/hostname/URL）。
            limit: 最多返回条数。
        """
        self.ensure_schema()
        conditions = ["started_at >= ?", "started_at <= ?"]
        params: list[Any] = [start, end]

        if probe_type:
            conditions.append("probe_type = ?")
            params.append(probe_type)
        if target:
            conditions.append("target LIKE ?")
            params.append(f'%"{target}"%')

        where_clause = " AND ".join(conditions)
        params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM probe_results
                WHERE {where_clause}
                ORDER BY started_at ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_probe_result(row) for row in rows]

    def get_probe_stats(
        self,
        *,
        probe_type: str,
        target: str | None,
        metric: str,
        start: str,
        end: str,
        granularity: str = "daily",
    ) -> list[dict[str, Any]]:
        """获取探针指标的聚合统计（按天/小时分组）。

        在 SQLite 层完成聚合，减少 Python 内存消耗。
        对于数值型指标计算 count/avg/min/max/p95。
        """
        self.ensure_schema()

        if granularity == "hourly":
            time_bucket = "substr(started_at, 1, 13) || ':00:00'"
        else:
            time_bucket = "substr(started_at, 1, 10) || 'T00:00:00'"

        conditions = ["probe_type = ?", "started_at >= ?", "started_at <= ?"]
        params: list[Any] = [probe_type, start, end]

        if target:
            conditions.append("target LIKE ?")
            params.append(f'%"{target}"%')

        where_clause = " AND ".join(conditions)

        # 使用 json_extract 从 observations JSON 中提取指标值
        # 只处理数值型指标
        sql = f"""
        SELECT
            {time_bucket} as time_bucket,
            COUNT(*) as count,
            AVG(CAST(json_extract(observations, '$.{metric}') AS REAL)) as avg,
            MIN(CAST(json_extract(observations, '$.{metric}') AS REAL)) as min,
            MAX(CAST(json_extract(observations, '$.{metric}') AS REAL)) as max
        FROM probe_results
        WHERE {where_clause}
          AND json_extract(observations, '$.{metric}') IS NOT NULL
          AND json_type(observations, '$.{metric}') IN ('integer', 'real')
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """

        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            values = dict(row)
            # p95 需要在 Python 层计算，SQLite 没有内置百分位函数
            # 先获取该分组的所有值
            bucket = values["time_bucket"]
            p95 = self._calculate_p95(
                connection=None,
                probe_type=probe_type,
                target=target,
                metric=metric,
                time_bucket=time_bucket,
                bucket_value=bucket,
                where_clause=where_clause,
                params=params,
            )
            results.append(
                {
                    "time_bucket": bucket,
                    "count": values["count"],
                    "avg": round(values["avg"], 2) if values["avg"] is not None else None,
                    "min": values["min"],
                    "max": values["max"],
                    "p95": p95,
                }
            )

        return results

    def _calculate_p95(
        self,
        *,
        connection: sqlite3.Connection | None,
        probe_type: str,
        target: str | None,
        metric: str,
        time_bucket: str,
        bucket_value: str,
        where_clause: str,
        params: list[Any],
    ) -> float | None:
        """计算某个时间分组内指标的 P95 值。"""
        # 重新构建查询参数（不包含 limit）
        p95_params: list[Any] = [probe_type] + params[1:]

        sql = f"""
        SELECT CAST(json_extract(observations, '$.{metric}') AS REAL) as val
        FROM probe_results
        WHERE {where_clause}
          AND {time_bucket} = ?
          AND json_extract(observations, '$.{metric}') IS NOT NULL
          AND json_type(observations, '$.{metric}') IN ('integer', 'real')
        ORDER BY val ASC
        """

        all_params = p95_params + [bucket_value]

        # 使用已有的 connection 或新建
        if connection is not None:
            rows = connection.execute(sql, all_params).fetchall()
        else:
            with self.connect() as conn:
                rows = conn.execute(sql, all_params).fetchall()

        if not rows:
            return None

        values = [row[0] for row in rows if row[0] is not None]
        if not values:
            return None

        # P95 计算
        import math
        n = len(values)
        if n == 1:
            return round(values[0], 2)

        rank = math.ceil(0.95 * n) - 1
        rank = max(0, min(rank, n - 1))
        return round(values[rank], 2)

    def get_status_distribution(
        self,
        *,
        probe_type: str,
        target: str | None,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        """获取探针状态分布统计。"""
        self.ensure_schema()

        conditions = ["probe_type = ?", "started_at >= ?", "started_at <= ?"]
        params: list[Any] = [probe_type, start, end]

        if target:
            conditions.append("target LIKE ?")
            params.append(f'%"{target}"%')

        where_clause = " AND ".join(conditions)

        sql = f"""
        SELECT status, COUNT(*) as count
        FROM probe_results
        WHERE {where_clause}
        GROUP BY status
        """

        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        distribution: dict[str, int] = {}
        total = 0
        for row in rows:
            values = dict(row)
            distribution[values["status"]] = values["count"]
            total += values["count"]

        success_count = distribution.get("success", 0)
        success_rate = round(success_count / total * 100, 1) if total > 0 else 0.0

        return {
            "total": total,
            "distribution": distribution,
            "success_count": success_count,
            "failed_count": distribution.get("failed", 0),
            "timeout_count": distribution.get("timeout", 0),
            "skipped_count": distribution.get("skipped", 0),
            "success_rate": success_rate,
        }

    # ------------------------------------------------------------------
    # Phase 9：工作流执行记录
    # ------------------------------------------------------------------

    def save_workflow_execution(self, execution: WorkflowExecution) -> None:
        """保存或更新工作流执行记录。"""
        self.ensure_schema()
        steps_json = json.dumps(
            [s.model_dump(mode="json") for s in execution.steps],
            ensure_ascii=False,
        )
        context_json = json.dumps(execution.context, ensure_ascii=False)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_executions
                    (id, workflow_name, status, trigger, steps,
                     started_at, ended_at, context, result_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    steps = excluded.steps,
                    ended_at = excluded.ended_at,
                    result_summary = excluded.result_summary
                """,
                (
                    execution.id,
                    execution.workflow_name,
                    execution.status.value,
                    execution.trigger,
                    steps_json,
                    execution.started_at.isoformat(),
                    execution.ended_at.isoformat() if execution.ended_at else None,
                    context_json,
                    execution.result_summary,
                ),
            )
            connection.commit()

    def get_workflow_execution(self, execution_id: str) -> WorkflowExecution | None:
        """按 ID 查找工作流执行记录。"""
        self.ensure_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        return self._row_to_workflow_execution(row) if row else None

    def list_workflow_executions(
        self,
        *,
        limit: int = 50,
        workflow_name: str | None = None,
        status: str | None = None,
    ) -> list[WorkflowExecution]:
        """查询工作流执行记录列表。"""
        self.ensure_schema()
        conditions: list[str] = []
        params: list[Any] = []

        if workflow_name:
            conditions.append("workflow_name = ?")
            params.append(workflow_name)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM workflow_executions
                {where_clause}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [self._row_to_workflow_execution(row) for row in rows]

    def _row_to_workflow_execution(self, row: Any) -> WorkflowExecution:
        """将数据库行转换为 WorkflowExecution 对象。"""
        steps_data = json.loads(row["steps"])
        steps = [
            WorkflowStepExecution(
                step_id=s["step_id"],
                action=s["action"],
                status=StepStatus(s["status"]),
                risk_level=RiskLevel(s["risk_level"]),
                started_at=datetime.fromisoformat(s["started_at"])
                if s.get("started_at")
                else None,
                ended_at=datetime.fromisoformat(s["ended_at"])
                if s.get("ended_at")
                else None,
                result=s.get("result"),
                error=s.get("error"),
                task_id=s.get("task_id"),
            )
            for s in steps_data
        ]

        context = json.loads(row["context"]) if row["context"] else {}

        return WorkflowExecution(
            id=row["id"],
            workflow_name=row["workflow_name"],
            status=WorkflowStatus(row["status"]),
            trigger=row["trigger"],
            steps=steps,
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"])
            if row["ended_at"]
            else None,
            context=context,
            result_summary=row["result_summary"],
        )
