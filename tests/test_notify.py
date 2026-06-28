import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from it_ops_toolkit.config import NotificationChannelConfig
from it_ops_toolkit.models import (
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    NotificationLog,
)
from it_ops_toolkit.notify import (
    DingTalkChannel,
    EmailChannel,
    FeishuChannel,
    NotificationCenter,
    NotificationError,
    WebhookChannel,
    WeComChannel,
    _render_markdown_summary,
    _render_webhook_payload,
    get_channel,
)
from it_ops_toolkit.storage import SQLiteStore


def _make_alert_event() -> AlertEvent:
    return AlertEvent(
        id="alert-test-001",
        rule_id="ping-loss",
        rule_name="Ping 丢包率超 10%",
        severity=AlertSeverity.warning,
        target="192.168.1.1",
        probe_type="ping",
        metric="packet_loss_percent",
        value="25.0",
        threshold="10",
        task_id="task-abc",
        triggered_at=datetime.now(UTC),
        status=AlertStatus.active,
    )


class ChannelRegistryTests(unittest.TestCase):
    def test_get_email_channel(self) -> None:
        ch = get_channel("email")
        self.assertIsInstance(ch, EmailChannel)

    def test_get_webhook_channel(self) -> None:
        ch = get_channel("webhook")
        self.assertIsInstance(ch, WebhookChannel)

    def test_get_wecom_channel(self) -> None:
        ch = get_channel("wecom")
        self.assertIsInstance(ch, WeComChannel)

    def test_get_dingtalk_channel(self) -> None:
        ch = get_channel("dingtalk")
        self.assertIsInstance(ch, DingTalkChannel)

    def test_get_feishu_channel(self) -> None:
        ch = get_channel("feishu")
        self.assertIsInstance(ch, FeishuChannel)

    def test_unknown_channel_raises(self) -> None:
        with self.assertRaises(NotificationError):
            get_channel("unknown")


class EmailChannelTests(unittest.TestCase):
    def test_missing_config_returns_error(self) -> None:
        ch = EmailChannel()
        result = ch.send(_make_alert_event(), {})
        self.assertFalse(result.success)
        self.assertIn("missing", result.error.lower())

    def test_send_success_with_mock(self) -> None:
        ch = EmailChannel()
        config = {
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_user": "user@example.com",
            "smtp_password": "pass",
            "from": "ops@example.com",
            "to": ["admin@example.com"],
            "use_ssl": False,
        }
        with patch("smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value.__enter__.return_value = instance
            result = ch.send(_make_alert_event(), config)
            self.assertTrue(result.success)
            instance.sendmail.assert_called_once()


class WebhookChannelTests(unittest.TestCase):
    def test_missing_url_returns_error(self) -> None:
        ch = WebhookChannel()
        result = ch.send(_make_alert_event(), {})
        self.assertFalse(result.success)
        self.assertIn("missing", result.error.lower())

    def test_send_success_with_mock(self) -> None:
        ch = WebhookChannel()
        config = {"url": "https://hooks.example.com/alert", "headers": {}}
        with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = ch.send(_make_alert_event(), config)
            self.assertTrue(result.success)

    def test_send_failure_with_mock(self) -> None:
        ch = WebhookChannel()
        config = {"url": "https://hooks.example.com/alert"}
        with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("connection refused")
            result = ch.send(_make_alert_event(), config)
            self.assertFalse(result.success)
            self.assertIn("connection refused", result.error)


class WeComChannelTests(unittest.TestCase):
    def test_missing_url_returns_error(self) -> None:
        ch = WeComChannel()
        result = ch.send(_make_alert_event(), {})
        self.assertFalse(result.success)

    def test_send_success_with_mock(self) -> None:
        ch = WeComChannel()
        config = {"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"}
        with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = ch.send(_make_alert_event(), config)
            self.assertTrue(result.success)


class DingTalkChannelTests(unittest.TestCase):
    def test_missing_url_returns_error(self) -> None:
        ch = DingTalkChannel()
        result = ch.send(_make_alert_event(), {})
        self.assertFalse(result.success)

    def test_send_success_with_mock(self) -> None:
        ch = DingTalkChannel()
        config = {"webhook_url": "https://oapi.dingtalk.com/robot/send"}
        with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = ch.send(_make_alert_event(), config)
            self.assertTrue(result.success)


class FeishuChannelTests(unittest.TestCase):
    def test_missing_url_returns_error(self) -> None:
        ch = FeishuChannel()
        result = ch.send(_make_alert_event(), {})
        self.assertFalse(result.success)

    def test_send_success_with_mock(self) -> None:
        ch = FeishuChannel()
        config = {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"}
        with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response
            result = ch.send(_make_alert_event(), config)
            self.assertTrue(result.success)


class TemplateRenderTests(unittest.TestCase):
    def test_webhook_payload_has_fields(self) -> None:
        event = _make_alert_event()
        payload = _render_webhook_payload(event)
        self.assertEqual(payload["alert_id"], "alert-test-001")
        self.assertEqual(payload["severity"], "warning")
        self.assertEqual(payload["rule"], "Ping 丢包率超 10%")
        self.assertEqual(payload["target"], "192.168.1.1")

    def test_markdown_summary_has_key_info(self) -> None:
        event = _make_alert_event()
        summary = _render_markdown_summary(event)
        self.assertIn("告警", summary)
        self.assertIn("192.168.1.1", summary)
        self.assertIn("25.0", summary)


class NotificationCenterTests(unittest.TestCase):
    def test_notify_sends_to_all_channels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            channels = [
                NotificationChannelConfig(
                    type="webhook",
                    enabled=True,
                    config={"url": "https://hooks.example.com/alert"},
                ),
            ]

            center = NotificationCenter(
                channels=channels, store=store, max_retries=1, retry_delay_seconds=0
            )

            with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.__enter__ = MagicMock(return_value=mock_response)
                mock_response.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_response

                results = center.notify(_make_alert_event())

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].success)

            # 检查审计日志
            logs = store.list_notification_logs()
            self.assertEqual(len(logs), 1)
            self.assertTrue(logs[0].success)
            self.assertEqual(logs[0].channel, "webhook")

    def test_notify_skips_disabled_channels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            channels = [
                NotificationChannelConfig(
                    type="webhook", enabled=False, config={"url": "..."}
                ),
                NotificationChannelConfig(
                    type="email", enabled=True, config={"smtp_host": "...", "to": []}
                ),
            ]

            center = NotificationCenter(
                channels=channels, store=store, max_retries=1, retry_delay_seconds=0
            )
            results = center.notify(_make_alert_event())

            # Only email channel (enabled), webhook is disabled
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].channel, "email")

    def test_notify_retries_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "ops.sqlite")
            store.ensure_schema()

            channels = [
                NotificationChannelConfig(
                    type="webhook",
                    enabled=True,
                    config={"url": "https://hooks.example.com/alert"},
                ),
            ]

            center = NotificationCenter(
                channels=channels, store=store, max_retries=3, retry_delay_seconds=0
            )

            with patch("it_ops_toolkit.notify.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = Exception("timeout")
                results = center.notify(_make_alert_event())

            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].success)
            self.assertEqual(results[0].retry_count, 2)  # 0-indexed, 3 attempts = max retry_count 2

            logs = store.list_notification_logs()
            self.assertEqual(len(logs), 1)
            self.assertFalse(logs[0].success)


if __name__ == "__main__":
    unittest.main()
