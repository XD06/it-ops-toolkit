from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator

DEFAULT_CONFIG_PATH = Path("ops.yaml")


class PingOptions(BaseModel):
    enabled: bool = True
    timeout_ms: int = Field(default=1000, gt=0)
    retries: int = Field(default=1, ge=0)


class ScanProfile(BaseModel):
    description: str = ""
    subnets: list[str] = Field(default_factory=list)
    ping: PingOptions = Field(default_factory=PingOptions)
    tcp_ports: list[int] = Field(default_factory=list)

    @field_validator("tcp_ports")
    @classmethod
    def validate_tcp_ports(cls, ports: list[int]) -> list[int]:
        invalid = [port for port in ports if port < 1 or port > 65535]
        if invalid:
            raise ValueError(f"invalid TCP ports: {invalid}")
        return ports


class HealthTarget(BaseModel):
    name: str
    type: Literal["ip", "hostname", "url", "service"]
    value: str | HttpUrl
    checks: list[Literal["ping", "dns", "tcp", "http"]]
    port: int | None = None

    @field_validator("port")
    @classmethod
    def validate_port(cls, port: int | None) -> int | None:
        if port is not None and (port < 1 or port > 65535):
            raise ValueError(f"invalid TCP port: {port}")
        return port


class HealthProfile(BaseModel):
    description: str = ""
    targets: list[HealthTarget] = Field(default_factory=list)


class ProbeDefaults(BaseModel):
    timeout_ms: int = Field(default=1000, gt=0)
    retries: int = Field(default=1, ge=0)
    concurrency: int = Field(default=32, gt=0)


class ReportsConfig(BaseModel):
    output_dir: Path = Path("./reports")
    formats: list[Literal["markdown", "csv", "json", "html"]] = Field(
        default_factory=lambda: ["markdown", "csv"]
    )


class StorageConfig(BaseModel):
    type: Literal["local", "sqlite"] = "sqlite"
    path: Path = Path("./data/ops.sqlite")


class SecurityConfig(BaseModel):
    risky_ports: list[int] = Field(default_factory=list)

    @field_validator("risky_ports")
    @classmethod
    def validate_risky_ports(cls, ports: list[int]) -> list[int]:
        invalid = [port for port in ports if port < 1 or port > 65535]
        if invalid:
            raise ValueError(f"invalid risky ports: {invalid}")
        return ports


# ---------------------------------------------------------------------------
# Phase 5：调度 / 告警 / 通知配置
# ---------------------------------------------------------------------------

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def _expand_env(value: Any) -> Any:
    """递归展开字符串中的 ${ENV_VAR} 占位符。"""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), value
        )
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


class ScheduleItemConfig(BaseModel):
    name: str
    task_type: Literal["health_check", "security_check", "asset_scan"] = "health_check"
    profile: str = "default"
    cron: str
    enabled: bool = True
    alert_on: list[str] = Field(default_factory=lambda: ["warning", "critical"])


class AlertRuleConditionConfig(BaseModel):
    probe_type: Literal["ping", "dns", "tcp", "http", "tls_cert"]
    metric: str
    operator: Literal["gt", "lt", "eq", "ne", "gte", "lte"]
    threshold: float | str


class AlertRuleItemConfig(BaseModel):
    id: str
    name: str
    enabled: bool = True
    condition: AlertRuleConditionConfig
    severity: Literal["info", "warning", "critical"] = "warning"
    cooldown_minutes: int = 60


class NotificationChannelConfig(BaseModel):
    type: Literal["email", "webhook", "wecom", "dingtalk", "feishu"]
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationsConfig(BaseModel):
    channels: list[NotificationChannelConfig] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 7：AI 配置
# ---------------------------------------------------------------------------


class OpenAIConfig(BaseModel):
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    timeout_seconds: int = 30


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    timeout_seconds: int = 30


class TemplateAIConfig(BaseModel):
    rules_dir: str | None = None


class AIConfig(BaseModel):
    backend: Literal["openai", "ollama", "template"] = "template"
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    template: TemplateAIConfig = Field(default_factory=TemplateAIConfig)
    timeout_seconds: int = 30


class AppConfig(BaseModel):
    name: str = "IT Ops Toolkit"
    environment: str = "local"


class OpsConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    scan_profiles: dict[str, ScanProfile] = Field(default_factory=dict)
    health_profiles: dict[str, HealthProfile] = Field(default_factory=dict)
    probe_defaults: ProbeDefaults = Field(default_factory=ProbeDefaults)
    reports: ReportsConfig = Field(default_factory=ReportsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    schedules: list[ScheduleItemConfig] = Field(default_factory=list)
    alert_rules: list[AlertRuleItemConfig] = Field(default_factory=list)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    ai: AIConfig = Field(default_factory=AIConfig)


DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "name": "IT Ops Toolkit",
        "environment": "local",
    },
    "scan_profiles": {
        "office_lan": {
            "description": "办公网段基础扫描",
            "subnets": ["192.168.1.0/24"],
            "ping": {
                "enabled": True,
                "timeout_ms": 1000,
                "retries": 1,
            },
            "tcp_ports": [22, 80, 443, 445, 3389],
        }
    },
    "health_profiles": {
        "daily_basic": {
            "description": "每日基础巡检",
            "targets": [
                {
                    "name": "默认网关",
                    "type": "ip",
                    "value": "192.168.1.1",
                    "checks": ["ping"],
                },
                {
                    "name": "DNS 基础解析",
                    "type": "hostname",
                    "value": "www.baidu.com",
                    "checks": ["dns"],
                },
                {
                    "name": "内网业务系统",
                    "type": "url",
                    "value": "https://intranet.example.local",
                    "checks": ["http"],
                },
            ],
        }
    },
    "probe_defaults": {
        "timeout_ms": 1000,
        "retries": 1,
        "concurrency": 32,
    },
    "reports": {
        "output_dir": "./reports",
        "formats": ["markdown", "csv"],
    },
    "storage": {
        "type": "sqlite",
        "path": "./data/ops.sqlite",
    },
    "security": {
        "risky_ports": [22, 445, 1433, 3306, 3389, 6379],
    },
    "schedules": [
        {
            "name": "每日早巡检",
            "task_type": "health_check",
            "profile": "daily_basic",
            "cron": "0 8 * * *",
            "enabled": True,
            "alert_on": ["warning", "critical"],
        },
    ],
    "alert_rules": [
        {
            "id": "ping-packet-loss",
            "name": "Ping 丢包率超 10%",
            "enabled": True,
            "condition": {
                "probe_type": "ping",
                "metric": "packet_loss_percent",
                "operator": "gt",
                "threshold": 10,
            },
            "severity": "warning",
            "cooldown_minutes": 60,
        },
        {
            "id": "cert-expiring",
            "name": "证书 14 天内过期",
            "enabled": True,
            "condition": {
                "probe_type": "tls_cert",
                "metric": "days_remaining",
                "operator": "lt",
                "threshold": 14,
            },
            "severity": "critical",
            "cooldown_minutes": 1440,
        },
        {
            "id": "port-down",
            "name": "TCP 端口不通",
            "enabled": True,
            "condition": {
                "probe_type": "tcp",
                "metric": "status",
                "operator": "eq",
                "threshold": "failed",
            },
            "severity": "critical",
            "cooldown_minutes": 30,
        },
    ],
    "notifications": {
        "channels": [],
    },
    "ai": {
        "backend": "template",
        "openai": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o-mini",
            "base_url": None,
            "timeout_seconds": 30,
        },
        "ollama": {
            "host": "http://localhost:11434",
            "model": "qwen2.5:7b",
            "timeout_seconds": 30,
        },
        "template": {
            "rules_dir": None,
        },
        "timeout_seconds": 30,
    },
}


class ConfigError(RuntimeError):
    pass


def create_default_config_file(path: Path, *, force: bool = False) -> Path:
    path = path.resolve()
    if path.exists() and not force:
        raise ConfigError(f"configuration already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(DEFAULT_CONFIG, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def load_config(path: Path) -> OpsConfig:
    path = path.resolve()
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw = _expand_env(raw)
        return OpsConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc}") from exc
