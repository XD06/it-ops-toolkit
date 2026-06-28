# 任务调度中心模块

## 模块职责

任务调度中心负责管理任务执行和定时调度。

中小企业运维场景中，定时巡检是核心需求——工具不能只靠手动触发，需要按配置的周期自动执行巡检，并在发现异常时触发告警。

## 现实场景

运维任务包括：

- 手动运行一次资产扫描。
- 手动运行一次巡检。
- 每天早上自动巡检。
- 每周生成一次报告。
- 故障时运行诊断流程。
- 未来 Agent 运行一个工作流。

这些都应该被记录成 TaskRun。

## 不负责什么

本模块不负责：

- 具体业务检查。
- 生成报告内容。
- 判断告警条件。
- 发送通知。
- 保存全部探测细节。

## 输入

输入可以包括：

- 任务类型。
- 目标。
- 参数。
- 调度策略（cron 表达式）。
- 超时。
- 重试。
- 执行人。

## 输出

输出应包括：

- 任务 ID。
- 任务状态。
- 开始时间。
- 结束时间。
- 结果引用。
- 错误摘要。
- 日志引用。
- 下次执行时间（定时任务）。

## 依赖模块

依赖：

- 数据存储。
- 权限与审计。
- 日志与观测性。
- 领域服务（`run_health_check`、`run_security_check`、`discover_assets`）。

被依赖：

- CLI。
- Web Console。
- Agent Runner。
- 通知中心（通过告警引擎间接依赖）。

## 架构设计（Phase 5）

### 进程内调度

采用 Python 进程内调度，不引入 Celery / Redis / 消息队列。

**理由**：
- 中小企业场景：单机部署，不需要分布式调度。
- 降低部署复杂度：不需要额外安装 Redis 或 RabbitMQ。
- 已有 Web Console（Uvicorn），调度器作为后台线程运行在同一进程。

**运行模式**：
- 调度器在 Web Console 启动时自动启动（`ops web run`）。
- 也支持独立 CLI 模式运行（`ops schedule run`），适合无 Web 环境的定时任务。
- 调度器通过 `SchedulerEngine` 类管理，支持动态添加/删除/暂停任务。

详细架构决策见 ADR-0008。

### 配置格式

```yaml
schedules:
  - name: "每日早巡检"
    task_type: "health_check"
    profile: "default"
    cron: "0 8 * * *"          # 每天早 8 点
    enabled: true
    alert_on: ["warning", "critical"]  # 触发告警的最低级别

  - name: "证书周检"
    task_type: "security_check"
    cron: "0 9 * * 1"           # 每周一早 9 点
    enabled: true
    alert_on: ["critical"]
```

### 数据模型

```python
class ScheduledTask(BaseModel):
    id: str
    name: str
    task_type: str           # health_check | security_check | asset_scan
    profile: str             # 巡检配置 profile
    cron: str                # cron 表达式
    enabled: bool
    alert_on: list[str]      # 触发告警的级别
    last_run: datetime | None
    next_run: datetime | None
    last_status: str | None  # success | failed | running
```

### 调度流程

```
配置文件 (schedules)
    ↓ 加载
调度器 (SchedulerEngine)
    ↓ 按周期触发
领域服务 (run_health_check / run_security_check)
    ↓ 产生
ProbeResult + Finding
    ↓ 评估
告警引擎 (AlertEngine)
    ↓ 生成
AlertEvent
    ↓ 发送
通知中心 (NotificationCenter)
```

### 持久化

- 调度任务定义存储在配置文件中。
- 调度运行状态（`last_run`、`next_run`、`last_status`）持久化到 SQLite。
- 进程重启后从 SQLite 恢复调度状态。
- 告警冷却状态持久化到 SQLite。

## Phase 5 实施计划

### 交付物

1. `SchedulerEngine` 类（`scheduler.py`）。
2. cron 表达式解析与下次执行时间计算。
3. 定时任务执行（调用领域服务）。
4. 调度状态持久化（SQLite）。
5. CLI `ops schedule` 命令组：
   - `ops schedule list`：列出所有定时任务。
   - `ops schedule add`：添加定时任务。
   - `ops schedule remove`：删除定时任务。
   - `ops schedule enable/disable`：启用/禁用定时任务。
   - `ops schedule run`：以独立模式运行调度器（无 Web）。
6. Web Console 调度管理页。
7. 告警引擎（`alert_engine.py`）：
   - `AlertRule` 模型。
   - `AlertEvent` 模型。
   - 规则评估逻辑。
   - 通知降噪（冷却期 + 去重 + 恢复通知）。
8. CLI `ops alert list / acknowledge` 命令。

### 告警规则

告警规则是数据，不是代码。规则存储在配置文件中。

```yaml
alert_rules:
  - id: "ping-packet-loss"
    name: "Ping 丢包率超 10%"
    enabled: true
    condition:
      probe_type: "ping"
      metric: "packet_loss_percent"
      operator: "gt"
      threshold: 10
    severity: "warning"
    cooldown_minutes: 60

  - id: "cert-expiring"
    name: "证书 14 天内过期"
    enabled: true
    condition:
      probe_type: "tls_cert"
      metric: "days_until_expiry"
      operator: "lt"
      threshold: 14
    severity: "critical"
    cooldown_minutes: 1440

  - id: "port-down"
    name: "TCP 端口不通"
    enabled: true
    condition:
      probe_type: "tcp"
      metric: "status"
      operator: "eq"
      threshold: "failed"
    severity: "critical"
    cooldown_minutes: 30
```

### 告警事件模型

```python
class AlertEvent(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    severity: str
    target: str              # 触发告警的目标
    probe_type: str
    metric: str
    value: str               # 实际值
    threshold: str           # 阈值
    task_id: str             # 关联的任务 ID
    triggered_at: datetime
    status: str              # active | resolved | suppressed
```

### 通知降噪策略

三层降噪：

1. **规则级冷却**：同一规则触发后，在 `cooldown_minutes` 内不重复发送。
2. **目标级去重**：同一目标 + 同一规则的告警，在冷却期内合并为一条。
3. **恢复通知**：告警状态从 active 变为 resolved 时，发送恢复通知。

## 验收标准

Phase 5 完成时，应满足：

- 能配置定时巡检并自动执行。
- 告警规则能触发通知。
- 通知能发送到至少邮件和 Webhook。
- 同一问题在恢复前不重复告警。
- 定时任务有审计记录。
- 调度器进程重启后能恢复调度状态。
- CLI 能管理定时任务（增删改查）。
- Web Console 能管理定时任务和查看告警。

## 未来扩展

后续可扩展：

- 任务队列与并发控制。
- 失败重试策略。
- 任务取消。
- Worker 模式（分布式调度）。
- SNMP trap / Syslog 被动告警接入。
- 告警升级（未确认时逐级通知）。
- 值班表与告警路由。
