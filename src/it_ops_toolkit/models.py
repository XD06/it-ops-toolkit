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
    probe_type: Literal["ping", "dns", "tcp", "http", "tls_cert"]
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
    owner: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class LocalInterface(BaseModel):
    name: str
    description: str | None = None
    status: str | None = None
    ipv4_addresses: list[str] = Field(default_factory=list)
    ipv6_addresses: list[str] = Field(default_factory=list)
    default_gateways: list[str] = Field(default_factory=list)
    dns_servers: list[str] = Field(default_factory=list)


class LocalSnapshot(BaseModel):
    id: str
    task_id: str
    collected_at: datetime
    hostname: str
    fqdn: str | None = None
    username: str | None = None
    os_name: str
    platform: str
    interfaces: list[LocalInterface] = Field(default_factory=list)
    default_routes: list[dict[str, Any]] = Field(default_factory=list)
    dns_servers: list[str] = Field(default_factory=list)
    proxy: dict[str, Any] = Field(default_factory=dict)
    observations: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class TaskRun(BaseModel):
    id: str
    task_type: Literal[
        "asset_scan",
        "asset_diff",
        "asset_import_notes",
        "automation",
        "health_matrix",
        "health_check",
        "diagnosis",
        "security_check",
        "report_generate",
        "ops_collect",
    ]
    requested_by: str = "local"
    source: Literal["cli", "web", "scheduler", "agent"] = "cli"
    status: TaskStatus = TaskStatus.pending
    risk_level: RiskLevel = RiskLevel.read_only
    started_at: datetime
    ended_at: datetime | None = None
    target_refs: list[str] = Field(default_factory=list)
    result_refs: list[str] = Field(default_factory=list)
    log_refs: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class Report(BaseModel):
    id: str
    source_task_id: str
    report_type: Literal["asset", "health", "diagnosis", "security", "ops", "generic"]
    title: str
    format: Literal["markdown", "csv", "json"]
    path: str
    summary: str = ""
    generated_at: datetime


class Finding(BaseModel):
    id: str
    task_id: str
    category: Literal["availability", "performance", "security", "configuration"]
    severity: Severity
    title: str
    description: str
    evidence_refs: list[str] = Field(default_factory=list)
    recommendation: str = ""
    requires_human_review: bool = True
