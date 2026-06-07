from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProbeStatus(StrEnum):
    success = "success"
    failed = "failed"
    timeout = "timeout"
    skipped = "skipped"


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class RiskLevel(StrEnum):
    read_only = "read_only"
    low_change = "low_change"
    high_change = "high_change"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Target(BaseModel):
    id: str | None = None
    type: Literal["ip", "hostname", "url", "subnet", "service"]
    value: str
    name: str | None = None
    tags: list[str] = Field(default_factory=list)
    owner: str | None = None
    description: str | None = None


class ErrorInfo(BaseModel):
    code: str
    message: str
    detail: str | None = None
    retryable: bool = False
    raw: str | None = None


class ProbeResult(BaseModel):
    id: str
    request_id: str | None = None
    task_id: str
    probe_type: Literal["ping", "dns", "tcp", "http"]
    target: Target
    status: ProbeStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    observations: dict[str, Any] = Field(default_factory=dict)
    error: ErrorInfo | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class Asset(BaseModel):
    id: str
    ip: str
    hostname: str | None = None
    mac: str | None = None
    vendor: str | None = None
    os_hint: str | None = None
    asset_type: str | None = None
    open_ports: list[int] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    status: Literal["active", "missing", "unknown"] = "active"
    source: str = "asset_scan"


class TaskRun(BaseModel):
    id: str
    task_type: Literal["asset_scan", "health_check", "diagnosis", "report_generate"]
    requested_by: str = "local"
    source: Literal["cli", "web", "scheduler", "agent"] = "cli"
    status: TaskStatus = TaskStatus.pending
    risk_level: RiskLevel = RiskLevel.read_only
    started_at: datetime
    ended_at: datetime | None = None
    target_refs: list[str] = Field(default_factory=list)
    result_refs: list[str] = Field(default_factory=list)
    log_refs: list[str] = Field(default_factory=list)
