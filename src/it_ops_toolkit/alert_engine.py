"""告警引擎：规则驱动，不硬编码。

告警引擎负责：
1. 遍历启用的 AlertRule。
2. 对每个 ProbeResult 检查是否匹配规则条件。
3. 匹配则生成 AlertEvent。
4. 检查冷却期：同一规则在同一目标的冷却期内，跳过（降噪）。
5. 检查恢复：如果之前有活跃告警但当前不再触发，则标记为 resolved。

告警引擎不负责：
- 发送通知（由通知中心负责）。
- 执行巡检（由调度器调用领域服务负责）。
- 判断严重程度（由 AlertRule 配置决定）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from .config import AlertRuleItemConfig
from .models import (
    AlertEvent,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    ProbeResult,
    ProbeStatus,
)
from .storage import SQLiteStore


class AlertEngineError(RuntimeError):
    pass


def _build_rule_from_config(item: AlertRuleItemConfig) -> AlertRule:
    """从配置项构建 AlertRule 模型。"""
    from .models import AlertCondition

    return AlertRule(
        id=item.id,
        name=item.name,
        enabled=item.enabled,
        condition=AlertCondition(
            probe_type=item.condition.probe_type,
            metric=item.condition.metric,
            operator=item.condition.operator,
            threshold=item.condition.threshold,
        ),
        severity=AlertSeverity(item.severity),
        cooldown_minutes=item.cooldown_minutes,
    )


def load_rules_from_config(rules_config: list[AlertRuleItemConfig]) -> list[AlertRule]:
    """从配置加载告警规则列表。"""
    return [_build_rule_from_config(item) for item in rules_config]


def _extract_metric_value(
    result: ProbeResult, metric: str
) -> float | str | None:
    """从 ProbeResult 的 observations 中提取指标值。"""
    observations: dict[str, Any] = result.observations

    # 特殊处理：status 指标直接取 ProbeResult 的状态
    if metric == "status":
        return result.status.value

    value = observations.get(metric)
    if value is None:
        return None

    # 尝试转为 float，如果失败则返回字符串
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return str(value)


def _compare(
    value: float | str,
    operator: str,
    threshold: float | str,
) -> bool:
    """比较值是否满足条件。"""
    # 尝试数值比较
    try:
        v = float(value)
        t = float(threshold)
        if operator == "gt":
            return v > t
        if operator == "lt":
            return v < t
        if operator == "gte":
            return v >= t
        if operator == "lte":
            return v <= t
        if operator == "eq":
            return v == t
        if operator == "ne":
            return v != t
    except (ValueError, TypeError):
        # 字符串比较
        v_str = str(value)
        t_str = str(threshold)
        if operator == "eq":
            return v_str == t_str
        if operator == "ne":
            return v_str != t_str
        # gt/lt/gte/lte 不适用于字符串
        return False

    return False


def evaluate_results(
    *,
    results: list[ProbeResult],
    rules: list[AlertRule],
    task_id: str,
    store: SQLiteStore,
    now: datetime | None = None,
) -> list[AlertEvent]:
    """评估探测结果，生成告警事件。

    流程：
    1. 遍历启用的规则。
    2. 对每个结果，检查 probe_type 是否匹配规则。
    3. 提取指标值，比较是否满足条件。
    4. 如果满足，检查冷却期（同一规则 + 同一目标是否有活跃告警且在冷却期内）。
    5. 不在冷却期则生成新的 AlertEvent 并持久化。
    6. 对于之前有活跃告警但现在不再触发的目标，标记为 resolved。

    返回新生成的 AlertEvent 列表（不包含被抑制的）。
    """
    if now is None:
        now = datetime.now(UTC)

    new_events: list[AlertEvent] = []
    enabled_rules = [r for r in rules if r.enabled]

    # 记录本轮触发过的 rule_id + target 组合（用于恢复检测）
    triggered_keys: set[tuple[str, str]] = set()

    for rule in enabled_rules:
        for result in results:
            if result.probe_type != rule.condition.probe_type:
                continue

            value = _extract_metric_value(result, rule.condition.metric)
            if value is None:
                continue

            matched = _compare(value, rule.condition.operator, rule.condition.threshold)
            target = result.target.value

            if matched:
                triggered_keys.add((rule.id, target))

                # 检查冷却期：是否有同一规则 + 同一目标的活跃告警
                existing = store.find_active_alert(rule.id, target)
                if existing:
                    # 检查是否在冷却期内
                    cooldown_ends = existing.triggered_at + timedelta(
                        minutes=rule.cooldown_minutes
                    )
                    if now < cooldown_ends:
                        # 在冷却期内，抑制
                        continue

                # 生成新告警事件
                event = AlertEvent(
                    id=f"alert-{uuid4().hex[:12]}",
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    target=target,
                    probe_type=rule.condition.probe_type,
                    metric=rule.condition.metric,
                    value=str(value),
                    threshold=str(rule.condition.threshold),
                    task_id=task_id,
                    triggered_at=now,
                    status=AlertStatus.active,
                )
                store.save_alert_event(event)
                new_events.append(event)

    # 恢复检测：之前有活跃告警但本轮不再触发的，标记为 resolved
    _check_resolutions(
        rules=enabled_rules,
        results=results,
        triggered_keys=triggered_keys,
        store=store,
        now=now,
    )

    return new_events


def _check_resolutions(
    *,
    rules: list[AlertRule],
    results: list[ProbeResult],
    triggered_keys: set[tuple[str, str]],
    store: SQLiteStore,
    now: datetime,
) -> None:
    """检查是否有告警应该被标记为恢复。

    对于每个规则，检查该规则下的所有活跃告警，
    如果告警的 target 在本轮结果中没有再触发，则标记为 resolved。
    """
    # 收集本轮所有探测过的 target（按 probe_type 分组）
    targets_by_probe: dict[str, set[str]] = {}
    for result in results:
        targets_by_probe.setdefault(result.probe_type, set()).add(result.target.value)

    for rule in rules:
        # 获取该规则下所有活跃告警
        # 我们需要按 target 检查，但 find_active_alert 只返回一条
        # 这里用一个变通方法：列出所有活跃告警然后过滤
        all_active = store.list_alert_events(status="active", limit=500)
        for event in all_active:
            if event.rule_id != rule.id:
                continue
            key = (rule.id, event.target)
            if key not in triggered_keys:
                # 该目标在本轮没有再触发告警
                # 只有当该目标在本轮确实被探测过时，才标记为恢复
                probe_targets = targets_by_probe.get(rule.condition.probe_type, set())
                if event.target in probe_targets:
                    resolved = event.model_copy(
                        update={
                            "status": AlertStatus.resolved,
                            "resolved_at": now,
                        }
                    )
                    store.save_alert_event(resolved)


def acknowledge_alert(
    *,
    event_id: str,
    store: SQLiteStore,
    now: datetime | None = None,
) -> AlertEvent:
    """确认告警事件。"""
    if now is None:
        now = datetime.now(UTC)

    event = store.get_alert_event(event_id)
    if event is None:
        raise AlertEngineError(f"alert event not found: {event_id}")

    acknowledged = event.model_copy(
        update={
            "acknowledged": True,
            "acknowledged_at": now,
        }
    )
    store.save_alert_event(acknowledged)
    return acknowledged
