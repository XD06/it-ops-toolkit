"""受控 Agent 工作流引擎。

设计原则：
- 工作流是预定义的，不是 AI 动态生成的。
- 每个 Action 标注风险等级，只读操作自动执行，变更操作需要审批。
- 每步执行都有审计记录。
- AI 辅助解释结果，不控制执行。

核心组件：
- Action 注册表：注册所有可执行的 Action。
- WorkflowEngine：解析工作流定义，按依赖顺序执行 Step。
- 内置工作流：预置常用运维工作流。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Callable

from .config import OpsConfig
from .models import (
    RiskLevel,
    StepStatus,
    TaskRun,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStepDef,
    WorkflowStepExecution,
    WorkflowStatus,
)
from .storage import SQLiteStore
from .tasks import new_task_run


class WorkflowError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Action 注册表
# ---------------------------------------------------------------------------

ActionCallable = Callable[..., dict[str, Any]]


class ActionRegistry:
    """Action 注册表：管理所有可执行的操作。"""

    def __init__(self) -> None:
        self._actions: dict[str, _ActionEntry] = {}

    def register(
        self,
        *,
        name: str,
        risk_level: RiskLevel = RiskLevel.read_only,
        description: str = "",
    ) -> Callable[[ActionCallable], ActionCallable]:
        """注册一个 Action。"""

        def decorator(func: ActionCallable) -> ActionCallable:
            self._actions[name] = _ActionEntry(
                func=func,
                risk_level=risk_level,
                description=description,
            )
            return func

        return decorator

    def get(self, name: str) -> _ActionEntry:
        if name not in self._actions:
            raise WorkflowError(f"unknown action: {name}")
        return self._actions[name]

    def list_actions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "risk_level": entry.risk_level.value,
                "description": entry.description,
            }
            for name, entry in sorted(self._actions.items())
        ]


class _ActionEntry:
    def __init__(
        self,
        *,
        func: ActionCallable,
        risk_level: RiskLevel,
        description: str,
    ) -> None:
        self.func = func
        self.risk_level = risk_level
        self.description = description


# 全局 Action 注册表
registry = ActionRegistry()


# ---------------------------------------------------------------------------
# 内置工作流定义
# ---------------------------------------------------------------------------


def get_builtin_workflows() -> list[WorkflowDefinition]:
    """返回内置工作流定义列表。"""
    return [
        WorkflowDefinition(
            name="network_troubleshoot",
            description="网络故障排查流程：互联网诊断 → DNS 诊断 → AI 总结",
            steps=[
                WorkflowStepDef(
                    id="diagnose_internet",
                    action="diagnose.internet",
                    risk_level=RiskLevel.read_only,
                    params={},
                ),
                WorkflowStepDef(
                    id="diagnose_dns",
                    action="diagnose.dns",
                    risk_level=RiskLevel.read_only,
                    params={"name": "www.baidu.com"},
                    depends_on=["diagnose_internet"],
                ),
                WorkflowStepDef(
                    id="ai_summarize",
                    action="ai.summarize_task",
                    risk_level=RiskLevel.read_only,
                    params={},
                    depends_on=["diagnose_internet", "diagnose_dns"],
                ),
            ],
            triggers=["manual", "cli", "web"],
        ),
        WorkflowDefinition(
            name="full_inspection",
            description="全面巡检流程：健康检查 → 安全检查 → AI 周报",
            steps=[
                WorkflowStepDef(
                    id="health_check",
                    action="health.check",
                    risk_level=RiskLevel.read_only,
                    params={},
                ),
                WorkflowStepDef(
                    id="security_check",
                    action="security.check",
                    risk_level=RiskLevel.read_only,
                    params={},
                    depends_on=["health_check"],
                ),
                WorkflowStepDef(
                    id="ai_weekly",
                    action="ai.summarize_recent",
                    risk_level=RiskLevel.read_only,
                    params={"days": 7},
                    depends_on=["health_check", "security_check"],
                ),
            ],
            triggers=["manual", "cli", "web", "schedule"],
        ),
        WorkflowDefinition(
            name="new_device_investigate",
            description="新设备调查流程：拓扑采集 → 未知设备检测 → AI 解释",
            steps=[
                WorkflowStepDef(
                    id="topology_arp",
                    action="topology.arp",
                    risk_level=RiskLevel.read_only,
                    params={},
                ),
                WorkflowStepDef(
                    id="security_check",
                    action="security.check",
                    risk_level=RiskLevel.read_only,
                    params={},
                    depends_on=["topology_arp"],
                ),
                WorkflowStepDef(
                    id="ai_explain",
                    action="ai.explain_anomaly",
                    risk_level=RiskLevel.read_only,
                    params={},
                    depends_on=["topology_arp", "security_check"],
                ),
            ],
            triggers=["manual", "cli", "web", "alert"],
        ),
    ]


def get_workflow_by_name(name: str) -> WorkflowDefinition:
    """按名称查找工作流定义。"""
    for wf in get_builtin_workflows():
        if wf.name == name:
            return wf
    raise WorkflowError(f"workflow not found: {name}")


def list_workflow_names() -> list[str]:
    """列出所有可用工作流名称。"""
    return [wf.name for wf in get_builtin_workflows()]


# ---------------------------------------------------------------------------
# 工作流执行引擎
# ---------------------------------------------------------------------------


def execute_workflow(
    *,
    workflow: WorkflowDefinition,
    store: SQLiteStore,
    config: OpsConfig,
    trigger: str = "manual",
    context: dict[str, Any] | None = None,
    auto_approve_low_risk: bool = False,
) -> WorkflowExecution:
    """执行工作流。

    Args:
        workflow: 工作流定义。
        store: 数据存储实例。
        config: 配置实例。
        trigger: 触发来源（manual / cli / web / alert）。
        context: 上下文参数，可覆盖 step params。
        auto_approve_low_risk: 是否自动批准低风险变更步骤。
            仅用于测试和 CLI --confirm 模式。

    Returns:
        WorkflowExecution 完整执行记录。
    """
    execution_id = f"wf-{uuid.uuid4().hex[:12]}"
    context = context or {}

    # 初始化步骤执行记录
    step_executions: dict[str, WorkflowStepExecution] = {}
    for step_def in workflow.steps:
        step_executions[step_def.id] = WorkflowStepExecution(
            step_id=step_def.id,
            action=step_def.action,
            risk_level=step_def.risk_level,
        )

    execution = WorkflowExecution(
        id=execution_id,
        workflow_name=workflow.name,
        status=WorkflowStatus.running,
        trigger=trigger,
        steps=list(step_executions.values()),
        started_at=datetime.now(UTC),
        context=context,
    )

    # 持久化初始状态
    store.save_workflow_execution(execution)
    task_id_map: dict[str, str] = {}

    try:
        for step_def in workflow.steps:
            # 检查依赖是否成功完成
            dep_failed = False
            for dep_id in step_def.depends_on:
                dep_exec = step_executions.get(dep_id)
                if dep_exec is None or dep_exec.status != StepStatus.success:
                    dep_failed = True
                    break

            if dep_failed:
                step_executions[step_def.id].status = StepStatus.skipped
                step_executions[step_def.id].ended_at = datetime.now(UTC)
                execution.steps = list(step_executions.values())
                store.save_workflow_execution(execution)
                continue

            # 风险检查
            if step_def.risk_level == RiskLevel.high_change:
                step_executions[step_def.id].status = StepStatus.rejected
                step_executions[step_def.id].error = (
                    "high_change actions are not supported in Phase 9"
                )
                step_executions[step_def.id].ended_at = datetime.now(UTC)
                execution.steps = list(step_executions.values())
                store.save_workflow_execution(execution)
                execution.status = WorkflowStatus.failed
                execution.result_summary = (
                    f"Step '{step_def.id}' rejected: high_change not supported"
                )
                execution.ended_at = datetime.now(UTC)
                store.save_workflow_execution(execution)
                return execution

            # 低风险变更需要审批
            needs_approval = (
                step_def.risk_level == RiskLevel.low_change
                and not auto_approve_low_risk
            )
            if needs_approval:
                step_executions[step_def.id].status = StepStatus.awaiting_approval
                execution.steps = list(step_executions.values())
                execution.status = WorkflowStatus.paused
                store.save_workflow_execution(execution)
                # 在实际场景中，这里会暂停等待外部审批
                # CLI 模式下由 --auto-approve 或交互确认
                # Web 模式下返回 pending 状态给前端
                continue

            # 执行 Action
            step_executions[step_def.id].status = StepStatus.running
            step_executions[step_def.id].started_at = datetime.now(UTC)
            execution.steps = list(step_executions.values())
            store.save_workflow_execution(execution)

            try:
                result = _execute_action(
                    step_def=step_def,
                    store=store,
                    config=config,
                    context=context,
                    task_id_map=task_id_map,
                )
                step_executions[step_def.id].status = StepStatus.success
                step_executions[step_def.id].result = result
                step_executions[step_def.id].ended_at = datetime.now(UTC)
                if "task_id" in result:
                    step_executions[step_def.id].task_id = result["task_id"]
                    task_id_map[step_def.id] = result["task_id"]

            except Exception as exc:
                step_executions[step_def.id].status = StepStatus.failed
                step_executions[step_def.id].error = str(exc)
                step_executions[step_def.id].ended_at = datetime.now(UTC)

                if step_def.stop_on_failure:
                    # 将后续未执行的步骤标记为 skipped
                    for future_step in workflow.steps:
                        if future_step.id not in step_executions:
                            continue
                        if step_executions[future_step.id].status == StepStatus.pending:
                            step_executions[future_step.id].status = StepStatus.skipped
                            step_executions[future_step.id].ended_at = datetime.now(UTC)
                    execution.steps = list(step_executions.values())
                    execution.status = WorkflowStatus.failed
                    execution.result_summary = (
                        f"Step '{step_def.id}' failed: {exc}"
                    )
                    execution.ended_at = datetime.now(UTC)
                    store.save_workflow_execution(execution)
                    return execution

            execution.steps = list(step_executions.values())
            store.save_workflow_execution(execution)

    except Exception as exc:
        execution.status = WorkflowStatus.failed
        execution.result_summary = f"Workflow error: {exc}"
        execution.ended_at = datetime.now(UTC)
        execution.steps = list(step_executions.values())
        store.save_workflow_execution(execution)
        return execution

    # 判断最终状态
    has_awaiting = any(
        s.status == StepStatus.awaiting_approval for s in step_executions.values()
    )
    if has_awaiting:
        execution.status = WorkflowStatus.paused
        execution.result_summary = "Workflow paused: awaiting approval"
    else:
        all_success = all(
            s.status in (StepStatus.success, StepStatus.skipped)
            for s in step_executions.values()
        )
        if all_success:
            execution.status = WorkflowStatus.success
            execution.result_summary = _build_summary(step_executions)
        else:
            execution.status = WorkflowStatus.failed
            execution.result_summary = _build_summary(step_executions)

    execution.ended_at = datetime.now(UTC)
    store.save_workflow_execution(execution)
    return execution


def _execute_action(
    *,
    step_def: WorkflowStepDef,
    store: SQLiteStore,
    config: OpsConfig,
    context: dict[str, Any],
    task_id_map: dict[str, str],
) -> dict[str, Any]:
    """执行单个 Action。"""
    # 合并参数：step params + context override
    params = {**step_def.params}
    # 用 context 中的值覆盖（如 trigger.target → name）
    for key, value in context.items():
        if key in params:
            params[key] = value

    action_name = step_def.action
    task = new_task_run(task_type=f"workflow_{action_name.replace('.', '_')}")
    store.save_task_run(task)

    if action_name == "diagnose.internet":
        from .diagnosis import run_internet_diagnosis

        results, summary = run_internet_diagnosis(
            task=task,
            store=store,
            **params,
        )
        return {
            "task_id": task.id,
            "probe_count": len(results),
            "title": summary.title,
            "likely_area": summary.likely_area,
            "recommendation": summary.recommendation,
        }

    elif action_name == "diagnose.dns":
        from .diagnosis import run_dns_diagnosis

        results, summary = run_dns_diagnosis(
            task=task,
            store=store,
            **params,
        )
        return {
            "task_id": task.id,
            "probe_count": len(results),
            "title": summary.title,
            "likely_area": summary.likely_area,
            "recommendation": summary.recommendation,
        }

    elif action_name == "diagnose.intranet":
        from .diagnosis import run_intranet_diagnosis

        results, summary = run_intranet_diagnosis(
            task=task,
            store=store,
            **params,
        )
        return {
            "task_id": task.id,
            "probe_count": len(results),
            "title": summary.title,
            "likely_area": summary.likely_area,
            "recommendation": summary.recommendation,
        }

    elif action_name == "health.check":
        from .health import run_health_check

        profile_name = params.pop("profile_name", "default")
        results = run_health_check(
            config=config,
            profile_name=profile_name,
            task=task,
            store=store,
        )
        return {
            "task_id": task.id,
            "probe_count": len(results),
        }

    elif action_name == "security.check":
        from .security import run_security_check

        findings = run_security_check(
            config=config,
            task=task,
            store=store,
        )
        return {
            "task_id": task.id,
            "finding_count": len(findings),
        }

    elif action_name == "topology.arp":
        from .probes.arp import collect_arp_table

        entries = collect_arp_table()
        return {
            "task_id": task.id,
            "arp_count": len(entries),
        }

    elif action_name == "ai.summarize_task":
        from .ai_copilot import summarize_task

        # 使用前一个诊断步骤的 task_id
        ref_task_id = _find_latest_task_id(task_id_map, step_def.depends_on)
        if ref_task_id is None:
            ref_task_id = task.id

        output = summarize_task(
            task_id=ref_task_id,
            store=store,
            config=config,
        )
        return {
            "task_id": task.id,
            "summary": output.summary,
            "backend": output.backend,
            "confidence": output.confidence,
        }

    elif action_name == "ai.summarize_recent":
        from .ai_copilot import summarize_recent

        days = params.get("days", 7)
        output = summarize_recent(
            store=store,
            config=config,
            days=days,
        )
        return {
            "task_id": task.id,
            "summary": output.summary,
            "backend": output.backend,
            "confidence": output.confidence,
        }

    elif action_name == "ai.explain_anomaly":
        from .ai_copilot import explain_anomaly

        ref_task_id = _find_latest_task_id(task_id_map, step_def.depends_on)
        if ref_task_id is None:
            ref_task_id = task.id

        output = explain_anomaly(
            task_id=ref_task_id,
            store=store,
            config=config,
        )
        return {
            "task_id": task.id,
            "summary": output.summary,
            "backend": output.backend,
            "confidence": output.confidence,
        }

    elif action_name == "report.generate":
        from .reports import generate_report
        from pathlib import Path

        ref_task_id = _find_latest_task_id(task_id_map, step_def.depends_on)
        if ref_task_id is None:
            ref_task_id = task.id

        report_format = params.get("format", "markdown")
        output_dir = Path(params.get("output_dir", "data/reports"))

        report = generate_report(
            store=store,
            source_task_id=ref_task_id,
            output_dir=output_dir,
            report_format=report_format,
        )
        return {
            "task_id": task.id,
            "report_id": report.id,
            "report_path": str(report.path),
        }

    else:
        raise WorkflowError(f"unknown action: {action_name}")


def _find_latest_task_id(
    task_id_map: dict[str, str],
    depends_on: list[str],
) -> str | None:
    """从依赖步骤中找到最新的 task_id。"""
    for dep_id in reversed(depends_on):
        if dep_id in task_id_map:
            return task_id_map[dep_id]
    return None


def _build_summary(step_executions: dict[str, WorkflowStepExecution]) -> str:
    """构建工作流执行结果摘要。"""
    total = len(step_executions)
    success = sum(1 for s in step_executions.values() if s.status == StepStatus.success)
    failed = sum(1 for s in step_executions.values() if s.status == StepStatus.failed)
    skipped = sum(1 for s in step_executions.values() if s.status == StepStatus.skipped)
    return f"Workflow completed: {success} success, {failed} failed, {skipped} skipped (total {total} steps)"
