"""根据配置创建告警通知器。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from app.core.notify_config import WeChatSettings
from app.notify.formatter import MarkdownAlertFormatter
from app.notify.notifier import NoopNotifier, Notifier
from app.notify.wechat import WeChatNotifier


class NotifierCreationError(RuntimeError):
    """通知器启动配置无效。"""


def _resolve_webhook(settings: WeChatSettings, environ: Mapping[str, str]) -> str:
    webhook = environ.get(settings.webhook_env, "").strip()
    if not webhook:
        raise NotifierCreationError(f"企业微信已启用，但环境变量 {settings.webhook_env} 未设置")
    parsed = urlsplit(webhook)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise NotifierCreationError("企业微信 webhook 必须是无用户信息的有效 HTTPS URL")
    return webhook


def create_notifier(
    settings: WeChatSettings,
    environ: Mapping[str, str] | None = None,
) -> Notifier:
    """通知关闭时返回无副作用实现，开启时严格解析密钥。"""

    if not settings.enabled:
        return NoopNotifier()
    webhook = _resolve_webhook(settings, os.environ if environ is None else environ)
    return WeChatNotifier(
        webhook_url=webhook,
        formatter=MarkdownAlertFormatter(),
        timeout_seconds=settings.timeout_seconds,
        max_attempts=settings.max_attempts,
        retry_backoff_seconds=settings.retry_backoff_seconds,
        max_total_seconds=settings.max_total_seconds,
    )
