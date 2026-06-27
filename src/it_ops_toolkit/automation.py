from __future__ import annotations

from typing import Any

from .adapters import flush_dns_cache
from .models import TaskRun


class AutomationError(RuntimeError):
    pass


def run_flush_dns_cache(
    *,
    task: TaskRun,
    dry_run: bool,
    confirm: bool,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    if not dry_run and not confirm:
        raise AutomationError("flush-dns requires --confirm when not running dry-run")
    if dry_run and confirm:
        raise AutomationError("choose either --dry-run or --confirm, not both")

    result = flush_dns_cache(dry_run=dry_run, timeout_seconds=timeout_seconds)
    executed = bool(result["executed"])
    status = str(result["status"])

    return {
        "scenario": "flush_dns",
        "scenario_label": "清理本机 DNS 缓存",
        "title": _flush_dns_title(dry_run=dry_run, status=status),
        "likely_area": "本机 DNS 缓存",
        "recommendation": _flush_dns_recommendation(
            dry_run=dry_run,
            executed=executed,
            status=status,
        ),
        "action": "flush_dns_cache",
        "target": "localhost",
        "dry_run": dry_run,
        "confirmed": confirm,
        "executed": executed,
        "risk_level": "low_change",
        "result": result,
        "result_id": f"automation-{task.id}-flush-dns",
    }


def _flush_dns_title(*, dry_run: bool, status: str) -> str:
    if dry_run:
        return "清理本机 DNS 缓存计划已生成"
    if status == "success":
        return "本机 DNS 缓存已清理"
    if status == "timeout":
        return "清理本机 DNS 缓存超时"
    return "清理本机 DNS 缓存失败"


def _flush_dns_recommendation(
    *,
    dry_run: bool,
    executed: bool,
    status: str,
) -> str:
    if dry_run:
        return "如确认要执行低风险变更，请重新运行并显式添加 --confirm。"
    if executed and status == "success":
        return "重新测试 DNS 解析或目标系统访问；如仍异常，继续执行 DNS 诊断。"
    return "查看错误信息；必要时以管理员权限运行，或手工检查本机 DNS Client 服务状态。"
