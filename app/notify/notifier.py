"""告警通知渠道的稳定抽象。"""

from __future__ import annotations

from typing import Protocol

from app.monitor.model import AlertEvent


class Notifier(Protocol):
    def send(self, alert: AlertEvent) -> None:
        """发送单个标准化告警事件。"""


class NoopNotifier:
    """通知关闭时使用，不执行网络请求或产生周期日志。"""

    def send(self, alert: AlertEvent) -> None:
        del alert
