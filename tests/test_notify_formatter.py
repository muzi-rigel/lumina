from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.market.model import InstrumentType
from app.monitor.model import (
    AlertEvent,
    AlertSeverity,
    RuleDirection,
    RuleType,
)
from app.notify.formatter import MarkdownAlertFormatter, MessageFormat

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 8, 10, 0, tzinfo=TZ)


def _alert(
    *,
    direction: RuleDirection = RuleDirection.RISE,
    reference_time: datetime | None = None,
    window_seconds: int | None = None,
) -> AlertEvent:
    return AlertEvent(
        code="510300",
        name="沪深300ETF",
        instrument_type=InstrumentType.ETF,
        rule_id="window-rise",
        rule_name="窗口上涨",
        rule_type=(
            RuleType.DAY_CHANGE_PERCENT
            if window_seconds is None
            else RuleType.WINDOW_CHANGE_PERCENT
        ),
        direction=direction,
        severity=AlertSeverity.WARNING,
        triggered_at=NOW,
        current_price=Decimal("4.12"),
        actual_change_percent=Decimal("1.234567"),
        threshold=Decimal("1.2"),
        window_seconds=window_seconds,
        reference_price=Decimal("4.07"),
        reference_time=reference_time,
        message="领域展示文本不应被直接复用",
    )


def test_formatter_builds_generic_markdown_for_day_rule() -> None:
    payload = MarkdownAlertFormatter().format(_alert())

    assert payload.format is MessageFormat.MARKDOWN
    assert "Lumina 市场异动" in payload.content
    assert "沪深300ETF（510300）" in payload.content
    assert "基准时间：昨收" in payload.content
    assert "实际涨跌：1.2346%" in payload.content
    assert "触发阈值：1.2000%" in payload.content
    assert "领域展示文本" not in payload.content


def test_formatter_uses_signed_fall_threshold_and_window_reference() -> None:
    reference_time = NOW.replace(minute=55)
    payload = MarkdownAlertFormatter().format(
        _alert(
            direction=RuleDirection.FALL,
            reference_time=reference_time,
            window_seconds=300,
        )
    )

    assert "触发阈值：-1.2000%" in payload.content
    assert f"基准时间：{reference_time.isoformat(timespec='seconds')}" in payload.content
    assert "窗口：300 秒" in payload.content


def test_formatter_removes_newlines_from_configured_names() -> None:
    alert = _alert()
    modified = replace(alert, name="名称\n注入", rule_name="规则\n注入")

    payload = MarkdownAlertFormatter().format(modified)

    assert "名称 注入" in payload.content
    assert "规则 注入" in payload.content
