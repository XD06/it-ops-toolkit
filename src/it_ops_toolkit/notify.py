"""通知中心：Adapter 模式，渠道可扩展。

通知中心负责把告警引擎产生的 AlertEvent 发送到配置的通知渠道。

通知中心不负责：
- 判断什么是异常（由告警引擎负责）。
- 生成报告内容。
- 管理用户权限。
"""

from __future__ import annotations

import json
import smtplib
import ssl
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

from .config import NotificationChannelConfig
from .models import AlertEvent, NotificationLog, NotificationResult
from .storage import SQLiteStore


class NotificationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 渠道接口
# ---------------------------------------------------------------------------


class NotificationChannel(ABC):
    """通知渠道抽象接口。"""

    @abstractmethod
    def send(
        self, event: AlertEvent, config: dict[str, Any]
    ) -> NotificationResult:
        """发送告警通知到指定渠道。"""
        ...


class EmailChannel(NotificationChannel):
    """邮件渠道：SMTP 发送。"""

    def send(
        self, event: AlertEvent, config: dict[str, Any]
    ) -> NotificationResult:
        sent_at = datetime.now(UTC)
        smtp_host = config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", 465))
        smtp_user = config.get("smtp_user", "")
        smtp_password = config.get("smtp_password", "")
        from_addr = config.get("from", smtp_user)
        to_addrs = config.get("to", [])
        use_ssl = config.get("use_ssl", True)

        if not smtp_host or not to_addrs:
            return NotificationResult(
                channel="email",
                success=False,
                error="missing smtp_host or to addresses",
                sent_at=sent_at,
            )

        subject = f"[ops-alert] {event.severity.value.upper()} - {event.rule_name}"
        body = _render_email_body(event)

        try:
            if use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    smtp_host, smtp_port, context=context, timeout=10
                ) as server:
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    server.sendmail(from_addr, to_addrs, _build_email(from_addr, to_addrs, subject, body))
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    server.sendmail(from_addr, to_addrs, _build_email(from_addr, to_addrs, subject, body))
            return NotificationResult(
                channel="email", success=True, sent_at=sent_at
            )
        except Exception as exc:
            return NotificationResult(
                channel="email",
                success=False,
                error=str(exc),
                sent_at=sent_at,
            )


class WebhookChannel(NotificationChannel):
    """Webhook 渠道：HTTP POST JSON。"""

    def send(
        self, event: AlertEvent, config: dict[str, Any]
    ) -> NotificationResult:
        sent_at = datetime.now(UTC)
        url = config.get("url", "")
        headers = config.get("headers", {})

        if not url:
            return NotificationResult(
                channel="webhook",
                success=False,
                error="missing webhook url",
                sent_at=sent_at,
            )

        payload = _render_webhook_payload(event)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            req = Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            for key, value in headers.items():
                req.add_header(key, str(value))
            with urlopen(req, timeout=10) as response:
                if 200 <= response.status < 300:
                    return NotificationResult(
                        channel="webhook", success=True, sent_at=sent_at
                    )
                return NotificationResult(
                    channel="webhook",
                    success=False,
                    error=f"HTTP {response.status}",
                    sent_at=sent_at,
                )
        except Exception as exc:
            return NotificationResult(
                channel="webhook",
                success=False,
                error=str(exc),
                sent_at=sent_at,
            )


class WeComChannel(NotificationChannel):
    """企业微信群机器人渠道。"""

    def send(
        self, event: AlertEvent, config: dict[str, Any]
    ) -> NotificationResult:
        sent_at = datetime.now(UTC)
        webhook_url = config.get("webhook_url", "")

        if not webhook_url:
            return NotificationResult(
                channel="wecom",
                success=False,
                error="missing webhook_url",
                sent_at=sent_at,
            )

        content = _render_markdown_summary(event)
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            req = Request(webhook_url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as response:
                if 200 <= response.status < 300:
                    return NotificationResult(
                        channel="wecom", success=True, sent_at=sent_at
                    )
                return NotificationResult(
                    channel="wecom",
                    success=False,
                    error=f"HTTP {response.status}",
                    sent_at=sent_at,
                )
        except Exception as exc:
            return NotificationResult(
                channel="wecom",
                success=False,
                error=str(exc),
                sent_at=sent_at,
            )


class DingTalkChannel(NotificationChannel):
    """钉钉群机器人渠道。"""

    def send(
        self, event: AlertEvent, config: dict[str, Any]
    ) -> NotificationResult:
        sent_at = datetime.now(UTC)
        webhook_url = config.get("webhook_url", "")

        if not webhook_url:
            return NotificationResult(
                channel="dingtalk",
                success=False,
                error="missing webhook_url",
                sent_at=sent_at,
            )

        content = _render_markdown_summary(event)
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": f"告警：{event.rule_name}", "text": content},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            req = Request(webhook_url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as response:
                if 200 <= response.status < 300:
                    return NotificationResult(
                        channel="dingtalk", success=True, sent_at=sent_at
                    )
                return NotificationResult(
                    channel="dingtalk",
                    success=False,
                    error=f"HTTP {response.status}",
                    sent_at=sent_at,
                )
        except Exception as exc:
            return NotificationResult(
                channel="dingtalk",
                success=False,
                error=str(exc),
                sent_at=sent_at,
            )


class FeishuChannel(NotificationChannel):
    """飞书群机器人渠道。"""

    def send(
        self, event: AlertEvent, config: dict[str, Any]
    ) -> NotificationResult:
        sent_at = datetime.now(UTC)
        webhook_url = config.get("webhook_url", "")

        if not webhook_url:
            return NotificationResult(
                channel="feishu",
                success=False,
                error="missing webhook_url",
                sent_at=sent_at,
            )

        content = _render_markdown_summary(event)
        payload = {
            "msg_type": "text",
            "content": {"text": content},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            req = Request(webhook_url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as response:
                if 200 <= response.status < 300:
                    return NotificationResult(
                        channel="feishu", success=True, sent_at=sent_at
                    )
                return NotificationResult(
                    channel="feishu",
                    success=False,
                    error=f"HTTP {response.status}",
                    sent_at=sent_at,
                )
        except Exception as exc:
            return NotificationResult(
                channel="feishu",
                success=False,
                error=str(exc),
                sent_at=sent_at,
            )


# ---------------------------------------------------------------------------
# 渠道注册
# ---------------------------------------------------------------------------

_CHANNEL_REGISTRY: dict[str, type[NotificationChannel]] = {
    "email": EmailChannel,
    "webhook": WebhookChannel,
    "wecom": WeComChannel,
    "dingtalk": DingTalkChannel,
    "feishu": FeishuChannel,
}


def get_channel(channel_type: str) -> NotificationChannel:
    """根据类型获取通知渠道实例。"""
    cls = _CHANNEL_REGISTRY.get(channel_type)
    if cls is None:
        raise NotificationError(f"unknown notification channel type: {channel_type}")
    return cls()


# ---------------------------------------------------------------------------
# 通知中心
# ---------------------------------------------------------------------------


class NotificationCenter:
    """通知中心：协调多渠道发送 + 重试 + 审计记录。"""

    def __init__(
        self,
        *,
        channels: list[NotificationChannelConfig],
        store: SQLiteStore,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        self._channel_configs = [ch for ch in channels if ch.enabled]
        self._store = store
        self._max_retries = max_retries
        self._retry_delay = retry_delay_seconds

    def notify(self, event: AlertEvent) -> list[NotificationResult]:
        """向所有启用的渠道发送告警通知。

        返回每个渠道的发送结果。
        """
        results: list[NotificationResult] = []

        for ch_config in self._channel_configs:
            result = self._send_with_retry(event, ch_config)
            results.append(result)

            # 记录审计日志
            log = NotificationLog(
                id=f"notif-{uuid4().hex[:12]}",
                alert_event_id=event.id,
                channel=result.channel,
                success=result.success,
                error=result.error,
                sent_at=result.sent_at,
                retry_count=result.retry_count,
            )
            self._store.save_notification_log(log)

        return results

    def _send_with_retry(
        self,
        event: AlertEvent,
        ch_config: NotificationChannelConfig,
    ) -> NotificationResult:
        """带重试的发送。"""
        channel = get_channel(ch_config.type)
        last_result: NotificationResult | None = None

        for attempt in range(self._max_retries):
            result = channel.send(event, ch_config.config)
            if result.success:
                return result.model_copy(update={"retry_count": attempt})
            last_result = result
            if attempt < self._max_retries - 1:
                time.sleep(self._retry_delay * (attempt + 1))

        if last_result:
            return last_result.model_copy(update={"retry_count": self._max_retries - 1})
        return NotificationResult(
            channel=ch_config.type,
            success=False,
            error="unknown error",
            sent_at=datetime.now(UTC),
            retry_count=self._max_retries - 1,
        )


# ---------------------------------------------------------------------------
# 消息模板
# ---------------------------------------------------------------------------


def _render_email_body(event: AlertEvent) -> str:
    """渲染邮件 HTML 正文。"""
    severity_color = {
        "critical": "#dc2626",
        "warning": "#f59e0b",
        "info": "#3b82f6",
    }.get(event.severity.value, "#6b7280")

    return f"""\
<div style="font-family: sans-serif;">
  <h2 style="color: {severity_color};">告警：{event.rule_name}</h2>
  <table style="border-collapse: collapse; width: 100%;">
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">严重程度</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd; color: {severity_color};">{event.severity.value.upper()}</td></tr>
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">目标</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd;">{event.target}</td></tr>
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">规则</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd;">{event.rule_name}</td></tr>
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">实际值</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd;">{event.value}</td></tr>
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">阈值</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd;">{event.threshold}</td></tr>
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">触发时间</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd;">{event.triggered_at}</td></tr>
    <tr><td style="padding: 4px 8px; border: 1px solid #ddd; font-weight: bold;">任务 ID</td>
        <td style="padding: 4px 8px; border: 1px solid #ddd;">{event.task_id}</td></tr>
  </table>
  <p style="color: #6b7280; font-size: 12px;">此邮件由 IT Ops Toolkit 自动发送。</p>
</div>
"""


def _build_email(
    from_addr: str, to_addrs: list[str], subject: str, body: str
) -> str:
    """构建邮件原始内容。"""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(body, "html", "utf-8"))
    return msg.as_string()


def _render_webhook_payload(event: AlertEvent) -> dict[str, Any]:
    """渲染 Webhook JSON 载荷。"""
    return {
        "alert_id": event.id,
        "severity": event.severity.value,
        "rule": event.rule_name,
        "rule_id": event.rule_id,
        "target": event.target,
        "probe_type": event.probe_type,
        "metric": event.metric,
        "value": event.value,
        "threshold": event.threshold,
        "triggered_at": event.triggered_at.isoformat(),
        "task_id": event.task_id,
        "status": event.status.value,
    }


def _render_markdown_summary(event: AlertEvent) -> str:
    """渲染群机器人 Markdown 摘要。"""
    severity_emoji = {
        "critical": "🔴",
        "warning": "🟡",
        "info": "🔵",
    }.get(event.severity.value, "⚪")

    lines = [
        f"{severity_emoji} **告警：{event.rule_name}**",
        f"",
        f"**严重程度**：{event.severity.value.upper()}",
        f"**目标**：{event.target}",
        f"**实际值**：{event.value}",
        f"**阈值**：{event.threshold}",
        f"**触发时间**：{event.triggered_at}",
        f"**任务 ID**：{event.task_id}",
    ]
    return "\n".join(lines)
