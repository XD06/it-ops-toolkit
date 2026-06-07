from __future__ import annotations

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
                    "name": "内部 DNS",
                    "type": "ip",
                    "value": "192.168.1.2",
                    "checks": ["ping", "dns"],
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
        return OpsConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc}") from exc
