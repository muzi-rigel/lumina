from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market.model import InstrumentType
from app.monitor.model import (
    AlertEvent,
    AlertSeverity,
    RuleDirection,
    RuleType,
)
from app.storage.models import AlertEventRecord, QuoteSnapshotRecord, serialize_utc
from tests.factories import make_quote

SHANGHAI = ZoneInfo("Asia/Shanghai")
QUOTE_TIME = datetime(2026, 8, 8, 9, 30, tzinfo=SHANGHAI)
CREATED_AT = datetime(2026, 8, 8, 1, 30, 1, 123456, tzinfo=UTC)


def _alert() -> AlertEvent:
    return AlertEvent(
        code="510300",
        name="沪深300ETF",
        instrument_type=InstrumentType.ETF,
        rule_id="day-fall",
        rule_name="日内下跌",
        rule_type=RuleType.DAY_CHANGE_PERCENT,
        direction=RuleDirection.FALL,
        severity=AlertSeverity.CRITICAL,
        triggered_at=QUOTE_TIME,
        current_price=Decimal("3.95"),
        actual_change_percent=Decimal("-1.25"),
        threshold=Decimal("1.0"),
        window_seconds=None,
        reference_price=Decimal("4"),
        reference_time=None,
        message="不应进入持久化模型",
    )


def test_quote_record_preserves_decimal_type_and_converts_utc() -> None:
    record = QuoteSnapshotRecord.from_quote(
        make_quote(QUOTE_TIME, price="10.123456789", previous_close="10"),
        CREATED_AT,
    )

    assert record.price == Decimal("10.123456789")
    assert record.change_pct == Decimal("1.2345678900")
    assert record.instrument_type == "ETF"
    assert record.quote_time == "2026-08-08T01:30:00.000000+00:00"
    assert record.created_at == "2026-08-08T01:30:01.123456+00:00"


def test_alert_record_contains_no_message_and_keeps_signed_change() -> None:
    record = AlertEventRecord.from_alert(_alert())

    assert record.name == "沪深300ETF"
    assert record.actual_change == Decimal("-1.25")
    assert record.threshold == Decimal("1.0")
    assert not hasattr(record, "message")


def test_serialize_utc_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="必须包含时区"):
        serialize_utc(datetime(2026, 8, 8, 9, 30))
