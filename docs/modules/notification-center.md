# 通知中心模块

## 模块职责

通知中心负责把需要提醒的信息发送到外部渠道。

它不判断什么是异常，只负责把告警引擎产生的 `AlertEvent` 发送到配置的通知渠道。

## 现实场景

中小企业运维常见通知需求：

- 每日巡检完成后发送摘要。
- 关键服务不可达时提醒值班人员。
- 发现未知设备时提醒。
- 证书快过期时提醒。
- 自动化任务失败时提醒。

常见渠道：

- 邮件。
- 企业微信。
- 钉钉。
- 飞书。
- Webhook。

## 不负责什么

本模块不负责：

- 执行巡检。
- 判断风险等级。
- 生成报告内容。
- 保存主要历史结果。
- 管理用户权限。
- 判断告警条件（由告警引擎负责）。

## 输入

输入可以包括：

- 告警事件（`AlertEvent`）。
- 目标渠道（配置决定）。
- 严重级别。
- 报告链接或文件路径。

## 输出

输出应包括：

- 发送状态。
- 渠道。
- 发送时间。
- 错误信息。
- 重试次数。

## 依赖模块

依赖：

- 配置中心。
- 数据存储。
- 日志与观测性。

被依赖：

- 告警引擎（`AlertEngine`）。
- 任务调度中心（通过告警引擎间接调用）。

## 架构设计（Phase 5）

### Adapter 模式

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

详细架构决策见 ADR-0008。

### 配置格式

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

### 通知渠道接口

```python
class NotificationChannel(ABC):
    @abstractmethod
    def send(self, event: AlertEvent, config: dict) -> NotificationResult:
        """发送告警通知到指定渠道。"""
        pass

class NotificationResult(BaseModel):
    channel: str           # 渠道类型
    success: bool          # 是否发送成功
    error: str | None      # 错误信息
    sent_at: datetime      # 发送时间
    retry_count: int       # 重试次数
```

### 通知模板

每个渠道有自己的消息格式模板：

- **邮件**：HTML 格式，包含摘要表格、严重程度标识、详情链接。
- **Webhook**：JSON 格式，包含 `AlertEvent` 关键字段。
- **群机器人**：Markdown 格式，简洁摘要 + 关键信息。

模板从 `AlertEvent` 和 `ProbeResult` 生成消息内容。

**邮件模板示例**：
```html
 Subject: [ops-alert] {{ severity }} - {{ rule_name }}
 
 <h2>告警：{{ rule_name }}</h2>
 <table>
   <tr><td>严重程度</td><td>{{ severity }}</td></tr>
   <tr><td>目标</td><td>{{ target }}</td></tr>
   <tr><td>规则</td><td>{{ rule_name }}</td></tr>
   <tr><td>实际值</td><td>{{ value }}</td></tr>
   <tr><td>阈值</td><td>{{ threshold }}</td></tr>
   <tr><td>触发时间</td><td>{{ triggered_at }}</td></tr>
   <tr><td>任务 ID</td><td>{{ task_id }}</td></tr>
 </table>
 <p>详情请查看 Web Console: <a href="{{ dashboard_url }}">查看</a></p>
```

**Webhook 模板示例**：
```json
{
  "alert_id": "{{ id }}",
  "severity": "{{ severity }}",
  "rule": "{{ rule_name }}",
  "target": "{{ target }}",
  "value": "{{ value }}",
  "threshold": "{{ threshold }}",
  "triggered_at": "{{ triggered_at }}",
  "task_id": "{{ task_id }}"
}
```

## Phase 5 实施计划

### 交付物

1. `NotificationChannel` 接口（`notify.py`）。
2. `EmailChannel` 实现（SMTP，使用标准库 `smtplib`）。
3. `WebhookChannel` 实现（HTTP POST，使用标准库 `urllib`）。
4. `WeComChannel` 实现（企业微信群机器人）。
5. `DingTalkChannel` 实现（钉钉群机器人）。
6. `FeishuChannel` 实现（飞书群机器人）。
7. 通知模板渲染。
8. 通知发送记录持久化（SQLite）。
9. 发送失败重试（最多 3 次，间隔递增）。

### 优先级

1. **EmailChannel** 和 **WebhookChannel** 优先实现（覆盖大部分场景）。
2. **WeComChannel** 和 **DingTalkChannel** 其次（国内企业常用）。
3. **FeishuChannel** 最后。

### 凭据管理

- SMTP 密码、Webhook Token、机器人 URL 从环境变量读取。
- 配置文件中使用 `${ENV_VAR}` 占位符，运行时替换。
- 不硬编码任何凭据。
- 凭据不出现在日志中。

## 验收标准

Phase 5 完成时，应满足：

- 通知事件结构已定义（`AlertEvent`）。
- 其他模块不直接调用具体通知渠道。
- 能发送到至少邮件和 Webhook。
- 通知渠道可扩展，新增渠道不改业务代码。
- 发送失败有重试。
- 通知发送有审计记录。
- 凭据从环境变量读取，不硬编码。

## 未来扩展

后续可扩展：

- 通知模板管理界面。
- 通知降噪（频率限制、合并发送）。
- 通知升级（未确认时逐级通知）。
- 值班表与通知路由。
- 每日摘要推送（非告警类通知）。
- 通知发送统计与报表。
