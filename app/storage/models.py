"""领域行情和告警对应的持久化记录模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.market.model import MarketQuote
from app.monitor.model import AlertEvent


def serialize_utc(timestamp: datetime) -> str:
    """将 aware datetime 统一保存为 UTC ISO 8601。"""

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("持久化时间必须包含时区")
    return timestamp.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True, slots=True)
class QuoteSnapshotRecord:
    code: str
    name: str
    instrument_type: str
    price: Decimal
    change_pct: Decimal | None
    volume: int
    quote_time: str
    created_at: str

    @classmethod
    def from_quote(
        cls,
        quote: MarketQuote,
        created_at: datetime,
    ) -> QuoteSnapshotRecord:
        return cls(
            code=quote.symbol,
            name=quote.name,
            instrument_type=quote.instrument.type.value,
            price=quote.price,
            change_pct=quote.change_percent,
            volume=quote.volume,
            quote_time=serialize_utc(quote.timestamp),
            created_at=serialize_utc(created_at),
        )


@dataclass(frozen=True, slots=True)
class AlertEventRecord:
    code: str
    name: str
    rule_id: str
    severity: str
    actual_change: Decimal
    threshold: Decimal
    trigger_time: str

    @classmethod
    def from_alert(cls, alert: AlertEvent) -> AlertEventRecord:
        return cls(
            code=alert.code,
            name=alert.name,
            rule_id=alert.rule_id,
            severity=alert.severity.value,
            actual_change=alert.actual_change_percent,
            threshold=alert.threshold,
            trigger_time=serialize_utc(alert.triggered_at),
        )
