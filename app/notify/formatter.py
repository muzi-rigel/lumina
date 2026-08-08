"""与具体通知渠道无关的告警消息格式化。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.monitor.formatting import format_percent
from app.monitor.model import AlertEvent, RuleDirection


class MessageFormat(StrEnum):
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"


@dataclass(frozen=True, slots=True)
class MessagePayload:
    format: MessageFormat
    content: str


class AlertFormatter(Protocol):
    def format(self, alert: AlertEvent) -> MessagePayload:
        """将告警转换为渠道可消费的通用消息载荷。"""


def _single_line(value: str) -> str:
    return " ".join(value.splitlines()).strip()


class MarkdownAlertFormatter:
    """生成简洁、可解释的通用 Markdown 告警消息。"""

    def format(self, alert: AlertEvent) -> MessagePayload:
        effective_threshold = (
            alert.threshold if alert.direction is RuleDirection.RISE else -alert.threshold
        )
        reference_time = (
            "昨收"
            if alert.reference_time is None
            else alert.reference_time.isoformat(timespec="seconds")
        )
        window = "日内" if alert.window_seconds is None else f"{alert.window_seconds} 秒"
        content = "\n".join(
            (
                "### Lumina 市场异动",
                f"> 级别：{alert.severity.value}",
                f"> 标的：{_single_line(alert.name)}（{alert.code}）",
                f"> 类型：{alert.instrument_type.value}",
                f"> 规则：{_single_line(alert.rule_name)} / {alert.direction.value}",
                f"> 当前价：{alert.current_price}",
                f"> 基准价：{alert.reference_price}",
                f"> 基准时间：{reference_time}",
                f"> 实际涨跌：{format_percent(alert.actual_change_percent)}%",
                f"> 触发阈值：{format_percent(effective_threshold)}%",
                f"> 窗口：{window}",
                f"> 触发时间：{alert.triggered_at.isoformat(timespec='seconds')}",
            )
        )
        return MessagePayload(format=MessageFormat.MARKDOWN, content=content)
