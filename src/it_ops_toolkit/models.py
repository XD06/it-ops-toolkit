from __future__ import annotations

from datetime import UTC, datetime
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
    probe_type: Literal["ping", "dns", "tcp", "http", "tls_cert", "snmp"]
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


# ---------------------------------------------------------------------------
# Phase 5：定时巡检与告警通知
# ---------------------------------------------------------------------------


class AlertSeverity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(StrEnum):
    active = "active"
    resolved = "resolved"
    suppressed = "suppressed"


class ScheduledTaskStatus(StrEnum):
    success = "success"
    failed = "failed"
    running = "running"


class AlertCondition(BaseModel):
    """告警规则的条件定义。"""

    probe_type: Literal["ping", "dns", "tcp", "http", "tls_cert", "snmp"]
    metric: str
    operator: Literal["gt", "lt", "eq", "ne", "gte", "lte"]
    threshold: float | str


class AlertRule(BaseModel):
    """告警规则：数据驱动，不硬编码。"""

    id: str
    name: str
    enabled: bool = True
    condition: AlertCondition
    severity: AlertSeverity = AlertSeverity.warning
    cooldown_minutes: int = 60


class AlertEvent(BaseModel):
    """告警事件：告警引擎评估后产生。"""

    id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    target: str
    probe_type: str
    metric: str
    value: str
    threshold: str
    task_id: str
    triggered_at: datetime
    status: AlertStatus = AlertStatus.active
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class ScheduledTask(BaseModel):
    """定时任务定义。"""

    id: str
    name: str
    task_type: Literal["health_check", "security_check", "asset_scan"] = "health_check"
    profile: str = "default"
    cron: str
    enabled: bool = True
    alert_on: list[AlertSeverity] = Field(default_factory=list)
    last_run: datetime | None = None
    next_run: datetime | None = None
    last_status: ScheduledTaskStatus | None = None
    last_task_id: str | None = None
    last_error: str | None = None


class NotificationResult(BaseModel):
    """通知发送结果。"""

    channel: str
    success: bool
    error: str | None = None
    sent_at: datetime
    retry_count: int = 0


class NotificationLog(BaseModel):
    """通知发送审计记录。"""

    id: str
    alert_event_id: str
    channel: str
    success: bool
    error: str | None = None
    sent_at: datetime
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Phase 7：AI 运维助手
# ---------------------------------------------------------------------------


class AIInput(BaseModel):
    """发送给 AI 的结构化数据。

    所有字段经过脱敏处理，不包含明文密码、Token、私钥。
    """

    task: TaskRun
    results: list[ProbeResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class AIOutput(BaseModel):
    """AI 返回的结构化结果。

    facts 和 inferences 严格分离：
    - facts 只能来自结构化数据。
    - inferences 是 AI 推理，必须标注。
    """

    summary: str
    facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    confidence: float = 1.0
    sources: list[str] = Field(default_factory=list)
    backend: str = "template"
    duration_ms: int | None = None


class AICallLog(BaseModel):
    """AI 调用审计记录。"""

    id: str
    task_id: str
    backend: str
    success: bool
    duration_ms: int
    error: str | None = None
    called_at: datetime


# ---------------------------------------------------------------------------
# Phase 8：网络拓扑与资产关系
# ---------------------------------------------------------------------------


class ArpEntry(BaseModel):
    """ARP 表条目：IP → MAC 映射。"""

    ip: str
    mac: str
    interface: str = ""
    state: str = "dynamic"
    vendor: str | None = None
    device_type: str | None = None


class TraceRouteHop(BaseModel):
    """Traceroute 单跳信息。"""

    hop: int
    ip: str | None = None
    rtt_ms: list[float] = Field(default_factory=list)
    timeout: bool = False


class TraceRouteResult(BaseModel):
    """Traceroute 完整结果。"""

    target: str
    source: str = ""
    hops: list[TraceRouteHop] = Field(default_factory=list)
    total_hops: int = 0
    reached: bool = False
    raw_output: str = ""


class AssetReconciliation(BaseModel):
    """ARP 表与资产库对比结果。"""

    new_devices: list[ArpEntry] = Field(default_factory=list)
    offline_devices: list[Asset] = Field(default_factory=list)
    matched: list[dict[str, Any]] = Field(default_factory=list)
    unknown_vendors: list[ArpEntry] = Field(default_factory=list)


class TopologyView(BaseModel):
    """拓扑视图：本机视角的网络结构。"""

    source: str = ""
    interfaces: list[dict[str, Any]] = Field(default_factory=list)
    gateway: str | None = None
    arp_entries: list[ArpEntry] = Field(default_factory=list)
    traceroute: TraceRouteResult | None = None
    reconciliation: AssetReconciliation | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Phase 9：受控 Agent 工作流
# ---------------------------------------------------------------------------


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    rejected = "rejected"


class WorkflowStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowStepDef(BaseModel):
    """工作流步骤定义。"""

    id: str
    action: str
    risk_level: RiskLevel = RiskLevel.read_only
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    condition: str | None = None
    stop_on_failure: bool = True


class WorkflowDefinition(BaseModel):
    """工作流定义。"""

    name: str
    description: str = ""
    steps: list[WorkflowStepDef] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=lambda: ["manual"])


class WorkflowStepExecution(BaseModel):
    """工作流步骤执行记录。"""

    step_id: str
    action: str
    status: StepStatus = StepStatus.pending
    risk_level: RiskLevel = RiskLevel.read_only
    started_at: datetime | None = None
    ended_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    task_id: str | None = None


class WorkflowExecution(BaseModel):
    """工作流执行记录。"""

    id: str
    workflow_name: str
    status: WorkflowStatus = WorkflowStatus.pending
    trigger: str = "manual"
    steps: list[WorkflowStepExecution] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
