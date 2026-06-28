# ADR 0008：定时巡检与告警通知架构

## 状态

已接受，作为 Phase 5（定时巡检与告警通知）的架构方向。

## 背景

Phase 1-4 的所有运维操作都是手动触发的（CLI 命令或 Web 按钮）。中小企业运维的核心痛点是"出问题了才知道"——没有人盯着的时候，网络中断、证书过期、端口异常都不会被发现，直到用户投诉。

要解决这个问题，需要两个能力：

1. **定时调度**：按配置的周期自动执行巡检，不需要人工触发。
2. **告警通知**：巡检发现异常时，主动通知运维人员。

这涉及三个新组件：
- 调度器（Scheduler）：管理定时任务的生命周期。
- 告警引擎（Alert Engine）：评估巡检结果是否触发告警规则。
- 通知中心（Notification Center）：把告警发送到外部渠道。

## 决策

### 1. 调度器：进程内调度，不做分布式

采用 Python 进程内调度，不引入 Celery / Redis / 消息队列。

**理由**：
- 中小企业场景：单机部署，不需要分布式调度。
- 降低部署复杂度：不需要额外安装 Redis 或 RabbitMQ。
- 已有 Web Console（Uvicorn），调度器作为后台线程运行在同一进程。

**实现**：
- 使用 `threading.Timer` 或 `schedule` 库实现周期调度。
- 调度器在 Web Console 启动时自动启动（`ops web run`）。
- 也支持独立 CLI 模式运行（`ops schedule run`），适合无 Web 环境的定时任务。
- 调度器通过 `SchedulerEngine` 类管理，支持动态添加/删除/暂停任务。

**配置格式**：
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

**任务状态模型**：
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

### 2. 告警引擎：规则驱动，不硬编码

告警规则是数据，不是代码。规则存储在配置文件中，告警引擎读取规则并评估。

**告警规则模型**：
```python
class AlertRule(BaseModel):
    id: str
    name: str
    enabled: bool
    condition: AlertCondition
    severity: str          # info | warning | critical
    cooldown_minutes: int  # 降噪：同一规则触发后冷却时间

class AlertCondition(BaseModel):
    probe_type: str           # ping | dns | tcp | http | tls_cert
    metric: str               # packet_loss_percent | avg_rtt_ms | status | days_until_expiry
    operator: str             # gt | lt | eq | ne | gte | lte
    threshold: float | str    # 阈值
```

**规则示例**：
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
    cooldown_minutes: 1440  # 24 小时

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

**评估流程**：
1. 巡检完成 → 产生 `list[ProbeResult]`。
2. 告警引擎遍历启用的 `AlertRule`。
3. 对每个结果，检查是否匹配规则条件。
4. 匹配则生成 `AlertEvent`。
5. 检查冷却期：如果同一规则在同一目标的冷却期内，跳过（降噪）。
6. 未在冷却期内的 `AlertEvent` 发送给通知中心。

**告警事件模型**：
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

### 3. 通知中心：Adapter 模式，渠道可扩展

通知渠道使用 Adapter 模式，新增渠道不改业务代码。

```
通知中心（notify()）
    ↓ 调用
NotificationChannel（接口）
    ↓ 实现
├── EmailChannel      → SMTP 发送邮件
├── WebhookChannel    → HTTP POST 到自定义 URL
├── WeComChannel      → 企业微信群机器人
├── DingTalkChannel   → 钉钉群机器人
└── FeishuChannel     → 飞书群机器人
```

**配置格式**：
```yaml
notifications:
  channels:
    - type: "email"
      enabled: true
      config:
        smtp_host: "smtp.example.com"
        smtp_port: 465
        smtp_user: "${SMTP_USER}"
        smtp_password: "${SMTP_PASSWORD}"
        from: "ops-alert@example.com"
        to: ["admin@example.com"]

    - type: "webhook"
      enabled: true
      config:
        url: "https://hooks.example.com/ops-alert"
        headers:
          Authorization: "Bearer ${WEBHOOK_TOKEN}"

    - type: "wecom"
      enabled: false
      config:
        webhook_url: "${WECOM_BOT_URL}"
```

**通知模板**：
- 每个渠道有自己的消息格式模板。
- 模板从 `AlertEvent` 和 `ProbeResult` 生成消息内容。
- 邮件：HTML 格式，包含摘要表格和详情链接。
- Webhook / 群机器人：JSON 格式，包含关键字段。

### 4. 通知降噪策略

三层降噪：

1. **规则级冷却**：同一规则触发后，在 `cooldown_minutes` 内不重复发送（配置在 AlertRule 中）。
2. **目标级去重**：同一目标 + 同一规则的告警，在冷却期内合并为一条（"192.168.1.1 丢包率持续超阈值"而不是每分钟一条）。
3. **恢复通知**：告警状态从 active 变为 resolved 时，发送一条恢复通知（"192.168.1.1 Ping 已恢复正常"）。

### 5. 架构边界

```
配置文件 (schedules + alert_rules + notifications)
    ↓ 加载
调度器 (SchedulerEngine)
    ↓ 触发
领域服务 (run_health_check / run_security_check)
    ↓ 产生
ProbeResult + Finding
    ↓ 评估
告警引擎 (AlertEngine)
    ↓ 生成
AlertEvent
    ↓ 发送
通知中心 (NotificationCenter)
    ↓ 分发
NotificationChannel (Email / Webhook / WeCom / ...)
```

关键原则：
- 调度器只负责"什么时候执行什么任务"，不负责判断结果。
- 告警引擎只负责"这个结果是否触发告警规则"，不负责发送通知。
- 通知中心只负责"把告警事件发到指定渠道"，不负责判断严重程度。
- 三者通过数据模型解耦，可独立测试。

## 备选方案

### 方案 B：使用 Celery + Redis 做分布式调度

优点：
- 支持分布式部署。
- 任务队列可靠。
- 支持任务重试和死信队列。

缺点：
- 部署复杂度高（需要 Redis）。
- 中小企业单机场景过度设计。
- 增加运维成本。

### 方案 C：使用系统 cron + CLI 脚本

优点：
- 零依赖，利用操作系统自带能力。
- 最简单。

缺点：
- 无法动态管理任务（需要改 crontab）。
- 告警逻辑散落在脚本中，不可审计。
- 无法与 Web Console 集成。
- Windows 不支持 cron（需要用 Task Scheduler）。

### 方案 D：使用 APScheduler 库

优点：
- 功能完善，支持 cron / interval / date 触发器。
- 纯 Python，无外部依赖。
- 支持持久化存储。

缺点：
- 引入新依赖（虽然轻量）。
- 可能与 Uvicorn 的事件循环冲突（需要使用 BackgroundScheduler 而非 AsyncIOScheduler）。

## 后果

正面影响：
- 工具从被动使用变成主动值守。
- 告警规则可配置，不硬编码。
- 通知渠道可扩展，新增渠道不改业务代码。
- 通知降噪避免告警风暴。
- 调度器与 Web Console 同进程，不需要额外部署。

负面影响：
- 进程内调度在进程重启时会丢失运行时状态（需要从持久化恢复）。
- 单进程调度不适合大量并发任务（中小企业场景可接受）。
- 需要维护告警规则和通知渠道的配置。
- 需要处理调度器与 Web Console 的线程安全问题。

## 执行要求

- 调度器实现为 `src/it_ops_toolkit/scheduler.py`。
- 告警引擎实现为 `src/it_ops_toolkit/alert_engine.py`。
- 通知中心实现为 `src/it_ops_toolkit/notify.py`。
- 调度状态持久化到 SQLite，进程重启后能恢复。
- 告警冷却状态持久化到 SQLite。
- CLI 新增 `ops schedule list / add / remove / enable / disable / run` 命令。
- CLI 新增 `ops alert list / acknowledge` 命令。
- Web Console 新增调度管理页和告警查看页。
- 通知渠道的凭据从环境变量读取，不硬编码在配置文件中。
- SMTP 和 Webhook 作为第一优先实现，群机器人后补。
