"""监控模块测试使用的类型化对象工厂。"""

from datetime import datetime
from decimal import Decimal

from app.market.model import InstrumentType, MarketInstrument, MarketQuote
from app.monitor.model import (
    AlertSeverity,
    RuleDefinition,
    RuleDirection,
    RuleTargets,
    RuleType,
)


def make_quote(
    timestamp: datetime,
    *,
    code: str = "510300",
    name: str = "沪深300ETF",
    instrument_type: InstrumentType = InstrumentType.ETF,
    price: str = "10",
    previous_close: str = "10",
) -> MarketQuote:
    current = Decimal(price)
    previous = Decimal(previous_close)
    return MarketQuote(
        instrument=MarketInstrument(code, name, instrument_type),
        timestamp=timestamp,
        source="test",
        price=current,
        previous_close=previous,
        open_price=previous,
        high_price=max(current, previous),
        low_price=min(current, previous),
        volume=100,
        turnover=Decimal("1000"),
    )


def make_rule(
    *,
    rule_id: str = "test-rule",
    rule_type: RuleType = RuleType.DAY_CHANGE_PERCENT,
    direction: RuleDirection = RuleDirection.RISE,
    threshold: str = "3",
    window_seconds: int | None = None,
    cooldown_seconds: int = 60,
    targets: RuleTargets | None = None,
) -> RuleDefinition:
    return RuleDefinition(
        id=rule_id,
        name=f"规则 {rule_id}",
        type=rule_type,
        enabled=True,
        direction=direction,
        threshold=Decimal(threshold),
        severity=AlertSeverity.WARNING,
        cooldown_seconds=cooldown_seconds,
        window_seconds=window_seconds,
        targets=targets or RuleTargets(),
    )
