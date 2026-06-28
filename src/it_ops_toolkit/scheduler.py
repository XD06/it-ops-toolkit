"""任务调度器：进程内调度，不做分布式。

调度器负责：
1. 管理 ScheduledTask 的生命周期。
2. 按 cron 表达式周期触发领域服务（run_health_check 等）。
3. 巡检完成后调用告警引擎评估结果。
4. 告警事件通过通知中心发送。

调度器不负责：
- 具体业务检查（由领域服务负责）。
- 判断告警条件（由告警引擎负责）。
- 发送通知（由通知中心负责）。
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from .alert_engine import evaluate_results, load_rules_from_config
from .config import OpsConfig, ScheduleItemConfig
from .health import HealthCheckError, run_health_check
from .models import (
    AlertSeverity,
    ProbeResult,
    ScheduledTask,
    ScheduledTaskStatus,
    TaskRun,
    TaskStatus,
)
from .notify import NotificationCenter
from .security import run_security_check
from .storage import SQLiteStore
from .tasks import finish_task_run, new_task_run


class SchedulerError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Cron 表达式解析
# ---------------------------------------------------------------------------


class CronExpression:
    """简化版 5 段 cron 表达式解析器。

    支持：分 时 日 月 周
    每段支持：* / 数字 / 逗号列表 / 范围 / 步长（*/n）
    """

    def __init__(self, expr: str) -> None:
        self._expr = expr.strip()
        parts = self._expr.split()
        if len(parts) != 5:
            raise SchedulerError(
                f"invalid cron expression (expected 5 fields): {expr}"
            )
        self._minute = self._parse_field(parts[0], 0, 59)
        self._hour = self._parse_field(parts[1], 0, 23)
        self._day = self._parse_field(parts[2], 1, 31)
        self._month = self._parse_field(parts[3], 1, 12)
        self._weekday = self._parse_field(parts[4], 0, 6)

    @staticmethod
    def _parse_field(field: str, min_val: int, max_val: int) -> set[int]:
        values: set[int] = set()
        for part in field.split(","):
            part = part.strip()
            # 步长：*/n
            if "/" in part:
                base, step_str = part.split("/", 1)
                step = int(step_str)
                if step <= 0:
                    raise SchedulerError(f"invalid step: {step}")
                if base == "*":
                    start, end = min_val, max_val
                elif "-" in base:
                    s, e = base.split("-", 1)
                    start, end = int(s), int(e)
                else:
                    start = int(base)
                    end = max_val
                for i in range(start, end + 1, step):
                    values.add(i)
            elif part == "*":
                values.update(range(min_val, max_val + 1))
            elif "-" in part:
                s, e = part.split("-", 1)
                for i in range(int(s), int(e) + 1):
                    values.add(i)
            else:
                values.add(int(part))

        # 验证范围
        for v in values:
            if v < min_val or v > max_val:
                raise SchedulerError(
                    f"value {v} out of range [{min_val}, {max_val}]"
                )
        return values

    def matches(self, dt: datetime) -> bool:
        """检查给定时间是否匹配 cron 表达式。

        注意：cron 周日=0，Python weekday() 周一=0，需要转换。
        cron_weekday = (python_weekday + 1) % 7
        """
        cron_weekday = (dt.weekday() + 1) % 7
        return (
            dt.minute in self._minute
            and dt.hour in self._hour
            and dt.day in self._day
            and dt.month in self._month
            and cron_weekday in self._weekday
        )

    def next_run_after(self, after: datetime) -> datetime:
        """计算从 after 之后的下一次匹配时间。"""
        # 从 after 的下一分钟开始检查
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # 最多检查 366 天
        max_iter = 366 * 24 * 60
        for _ in range(max_iter):
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise SchedulerError(
            f"no next run found within 366 days for: {self._expr}"
        )


# ---------------------------------------------------------------------------
# 调度器引擎
# ---------------------------------------------------------------------------


class SchedulerEngine:
    """进程内调度引擎。

    使用后台线程轮询定时任务，到时间后触发领域服务执行。
    支持通过 CLI 独立运行，也可以在 Web Console 启动时自动启动。
    """

    def __init__(
        self,
        *,
        config: OpsConfig,
        store: SQLiteStore,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._config = config
        self._store = store
        self._poll_interval = poll_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._tasks: list[ScheduledTask] = []
        self._load_tasks()

    def _load_tasks(self) -> None:
        """从配置和持久化状态加载定时任务。"""
        # 先从持久化存储加载已有任务
        existing = {t.id: t for t in self._store.list_scheduled_tasks()}

        self._tasks = []
        for item in self._config.schedules:
            task_id = f"schedule-{item.name}"
            cron = CronExpression(item.cron)
            now = datetime.now(UTC)

            # 如果持久化存储中有状态，复用
            if task_id in existing:
                task = existing[task_id]
                # 更新配置（可能被 CLI 修改过）
                task = task.model_copy(
                    update={
                        "name": item.name,
                        "task_type": item.task_type,
                        "profile": item.profile,
                        "cron": item.cron,
                        "enabled": item.enabled,
                        "alert_on": [AlertSeverity(s) for s in item.alert_on],
                    }
                )
            else:
                task = ScheduledTask(
                    id=task_id,
                    name=item.name,
                    task_type=item.task_type,
                    profile=item.profile,
                    cron=item.cron,
                    enabled=item.enabled,
                    alert_on=[AlertSeverity(s) for s in item.alert_on],
                    next_run=cron.next_run_after(now),
                )
            self._tasks.append(task)
            self._store.save_scheduled_task(task)

    def list_tasks(self) -> list[ScheduledTask]:
        """列出所有定时任务。"""
        with self._lock:
            return list(self._tasks)

    def get_task(self, task_id: str) -> ScheduledTask | None:
        """获取单个定时任务。"""
        with self._lock:
            for task in self._tasks:
                if task.id == task_id:
                    return task
        return None

    def add_task(self, task: ScheduledTask) -> None:
        """添加定时任务。"""
        # 验证 cron 表达式
        cron = CronExpression(task.cron)
        if task.next_run is None:
            task = task.model_copy(
                update={"next_run": cron.next_run_after(datetime.now(UTC))}
            )
        with self._lock:
            self._tasks.append(task)
        self._store.save_scheduled_task(task)

    def remove_task(self, task_id: str) -> bool:
        """删除定时任务。"""
        with self._lock:
            before = len(self._tasks)
            self._tasks = [t for t in self._tasks if t.id != task_id]
            removed = len(self._tasks) < before
        if removed:
            self._store.delete_scheduled_task(task_id)
        return removed

    def enable_task(self, task_id: str) -> ScheduledTask | None:
        """启用定时任务。"""
        return self._set_enabled(task_id, True)

    def disable_task(self, task_id: str) -> ScheduledTask | None:
        """禁用定时任务。"""
        return self._set_enabled(task_id, False)

    def _set_enabled(self, task_id: str, enabled: bool) -> ScheduledTask | None:
        with self._lock:
            for i, task in enumerate(self._tasks):
                if task.id == task_id:
                    updated = task.model_copy(update={"enabled": enabled})
                    if enabled and updated.next_run is None:
                        cron = CronExpression(updated.cron)
                        updated = updated.model_copy(
                            update={"next_run": cron.next_run_after(datetime.now(UTC))}
                        )
                    self._tasks[i] = updated
                    self._store.save_scheduled_task(updated)
                    return updated
        return None

    def run_task_now(self, task_id: str) -> ScheduledTask | None:
        """立即执行一次定时任务（不等调度时间）。"""
        with self._lock:
            task = None
            for t in self._tasks:
                if t.id == task_id:
                    task = t
                    break
            if task is None:
                return None

        self._execute_task(task)
        return self.get_task(task_id)

    def start(self) -> None:
        """启动调度器后台线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止调度器。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def run_forever(self) -> None:
        """以阻塞模式运行调度器（CLI `ops schedule run` 使用）。"""
        self._stop_event.clear()
        self._run_loop()

    def _run_loop(self) -> None:
        """调度循环：轮询定时任务，到时间则执行。"""
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                # 调度循环不应因单个任务失败而退出
                pass
            self._stop_event.wait(self._poll_interval)

    def _poll(self) -> None:
        """检查一次所有定时任务是否到执行时间。"""
        now = datetime.now(UTC)
        with self._lock:
            tasks_to_run = [
                t
                for t in self._tasks
                if t.enabled and t.next_run is not None and t.next_run <= now
            ]

        for task in tasks_to_run:
            self._execute_task(task)

    def _execute_task(self, task: ScheduledTask) -> None:
        """执行单个定时任务。

        1. 标记为 running。
        2. 调用对应的领域服务。
        3. 评估告警。
        4. 发送通知。
        5. 更新任务状态和下次执行时间。
        """
        now = datetime.now(UTC)

        # 标记为 running
        running = task.model_copy(
            update={
                "last_run": now,
                "last_status": ScheduledTaskStatus.running,
                "last_error": None,
            }
        )
        self._update_task(running)

        task_run = new_task_run(
            task_type=task.task_type,
            requested_by="scheduler",
        )
        task_run = task_run.model_copy(update={"source": "scheduler"})
        self._store.save_task_run(task_run)

        results: list[ProbeResult] = []
        error_msg: str | None = None

        try:
            if task.task_type == "health_check":
                results = run_health_check(
                    config=self._config,
                    profile_name=task.profile,
                    task=task_run,
                    store=self._store,
                )
            elif task.task_type == "security_check":
                run_security_check(
                    config=self._config,
                    task=task_run,
                    store=self._store,
                )
            elif task.task_type == "asset_scan":
                # 资产扫描需要导入 assets 模块
                from .assets import run_asset_scan

                run_asset_scan(
                    config=self._config,
                    profile_name=task.profile,
                    task=task_run,
                    store=self._store,
                )
            else:
                raise SchedulerError(f"unknown task type: {task.task_type}")

            # 完成任务
            completed = finish_task_run(task_run, status=TaskStatus.success)
            self._store.save_task_run(completed)

        except HealthCheckError as exc:
            error_msg = str(exc)
            completed = finish_task_run(task_run, status=TaskStatus.failed)
            self._store.save_task_run(completed)
        except Exception as exc:
            error_msg = str(exc)
            completed = finish_task_run(task_run, status=TaskStatus.failed)
            self._store.save_task_run(completed)

        # 评估告警
        if results and task.alert_on:
            rules = load_rules_from_config(self._config.alert_rules)
            events = evaluate_results(
                results=results,
                rules=rules,
                task_id=task_run.id,
                store=self._store,
            )

            # 过滤告警级别
            alert_severities = set(task.alert_on)
            events_to_notify = [
                e for e in events if e.severity in alert_severities
            ]

            # 发送通知
            if events_to_notify:
                notification_center = NotificationCenter(
                    channels=self._config.notifications.channels,
                    store=self._store,
                )
                for event in events_to_notify:
                    notification_center.notify(event)

        # 更新任务状态
        cron = CronExpression(task.cron)
        next_run = cron.next_run_after(now)

        finished = task.model_copy(
            update={
                "last_run": now,
                "last_status": ScheduledTaskStatus.failed if error_msg else ScheduledTaskStatus.success,
                "last_task_id": task_run.id,
                "last_error": error_msg,
                "next_run": next_run,
            }
        )
        self._update_task(finished)

    def _update_task(self, task: ScheduledTask) -> None:
        """更新内存和持久化中的任务。"""
        with self._lock:
            for i, t in enumerate(self._tasks):
                if t.id == task.id:
                    self._tasks[i] = task
                    break
        self._store.save_scheduled_task(task)


def create_scheduled_task(
    *,
    name: str,
    task_type: str,
    profile: str,
    cron: str,
    enabled: bool = True,
    alert_on: list[str] | None = None,
) -> ScheduledTask:
    """创建一个新的 ScheduledTask 实例。"""
    if alert_on is None:
        alert_on = ["warning", "critical"]

    cron_expr = CronExpression(cron)
    now = datetime.now(UTC)

    return ScheduledTask(
        id=f"schedule-{name}",
        name=name,
        task_type=task_type,
        profile=profile,
        cron=cron,
        enabled=enabled,
        alert_on=[AlertSeverity(s) for s in alert_on],
        next_run=cron_expr.next_run_after(now),
    )
