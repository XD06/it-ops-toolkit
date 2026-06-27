from __future__ import annotations

from .config import OpsConfig
from .models import Asset, Finding, ProbeResult, ProbeStatus, Severity, TaskRun
from .probes import check_tls_certificate
from .storage import SQLiteStore


HIGH_RISK_PORTS = {3389, 445, 1433, 3306, 6379}
MEDIUM_RISK_PORTS = {22}
CERT_EXPIRING_SOON_DAYS = 30


def run_security_check(
    *,
    config: OpsConfig,
    task: TaskRun,
    store: SQLiteStore,
) -> list[Finding]:
    assets = store.list_assets()
    risky_ports = set(config.security.risky_ports)
    findings: list[Finding] = []

    for asset in assets:
        findings.extend(_find_risky_ports(task=task, asset=asset, risky_ports=risky_ports))

    for finding in findings:
        store.save_finding(finding)
    return findings


def run_certificate_check(
    *,
    task: TaskRun,
    store: SQLiteStore,
    hostname: str,
    port: int = 443,
    warning_days: int = CERT_EXPIRING_SOON_DAYS,
    timeout_ms: int = 1000,
) -> tuple[ProbeResult, list[Finding]]:
    result = check_tls_certificate(
        task_id=task.id,
        hostname=hostname,
        port=port,
        timeout_ms=timeout_ms,
    )
    store.save_probe_result(result)
    findings = _find_certificate_risks(
        task=task,
        result=result,
        warning_days=warning_days,
    )
    for finding in findings:
        store.save_finding(finding)
    return result, findings


def _find_risky_ports(
    *,
    task: TaskRun,
    asset: Asset,
    risky_ports: set[int],
) -> list[Finding]:
    findings: list[Finding] = []
    for port in sorted(set(asset.open_ports) & risky_ports):
        severity = _severity_for_port(port)
        findings.append(
            Finding(
                id=f"finding-risky-port-{asset.ip}-{port}",
                task_id=task.id,
                category="security",
                severity=severity,
                title=f"发现高风险端口开放：{port}",
                description=f"资产 {asset.ip} 开放了风险端口 {port}。",
                evidence_refs=[asset.id],
                recommendation=_recommendation_for_port(port),
                requires_human_review=True,
            )
        )
    return findings


def _severity_for_port(port: int) -> Severity:
    if port in HIGH_RISK_PORTS:
        return Severity.high
    if port in MEDIUM_RISK_PORTS:
        return Severity.medium
    return Severity.low


def _recommendation_for_port(port: int) -> str:
    if port == 3389:
        return "确认 RDP 是否必须开放；限制来源网段，优先使用 VPN 或堡垒机。"
    if port == 445:
        return "确认 SMB 是否必须开放；避免跨网段暴露，检查共享权限。"
    if port in {1433, 3306, 6379}:
        return "确认数据库或缓存服务是否必须开放；限制来源、启用认证并检查防火墙策略。"
    if port == 22:
        return "确认 SSH 是否必须开放；限制来源、禁用弱口令并优先使用密钥认证。"
    return "确认该端口业务用途，限制来源并记录负责人。"


def _find_certificate_risks(
    *,
    task: TaskRun,
    result: ProbeResult,
    warning_days: int,
) -> list[Finding]:
    target = result.target.value
    if result.status != ProbeStatus.success:
        return [
            Finding(
                id=f"finding-cert-check-failed-{target}",
                task_id=task.id,
                category="security",
                severity=Severity.medium,
                title="TLS 证书检查失败",
                description=f"目标 {target} 的 TLS 证书检查失败。",
                evidence_refs=[result.id],
                recommendation="确认目标端口是否开放、是否启用 TLS、证书链是否完整，以及本机是否信任相关 CA。",
                requires_human_review=True,
            )
        ]

    days_remaining = int(result.observations.get("days_remaining", 0))
    if days_remaining < 0:
        return [
            Finding(
                id=f"finding-cert-expired-{target}",
                task_id=task.id,
                category="security",
                severity=Severity.high,
                title="TLS 证书已过期",
                description=f"目标 {target} 的 TLS 证书已过期 {abs(days_remaining)} 天。",
                evidence_refs=[result.id],
                recommendation="尽快更新证书并确认服务已加载新证书，检查自动续期任务是否失败。",
                requires_human_review=True,
            )
        ]
    if days_remaining <= warning_days:
        return [
            Finding(
                id=f"finding-cert-expiring-{target}",
                task_id=task.id,
                category="security",
                severity=Severity.medium,
                title="TLS 证书即将过期",
                description=f"目标 {target} 的 TLS 证书将在 {days_remaining} 天后过期。",
                evidence_refs=[result.id],
                recommendation="安排证书续期，确认自动续期、证书部署和服务重载流程正常。",
                requires_human_review=True,
            )
        ]
    return []
