from datetime import UTC, datetime
from decimal import Decimal

from app.market.model import InstrumentType, MarketInstrument, MarketQuote
from app.monitor.engine import MonitorEngine
from app.monitor.rules import MonitorRule, RuleResult


class BrokenRule(MonitorRule):
    @property
    def name(self) -> str:
        return "broken"

    def evaluate(self, quote: MarketQuote) -> RuleResult:
        del quote
        raise ValueError("模拟坏数据")


class TriggerRule(MonitorRule):
    @property
    def name(self) -> str:
        return "trigger"

    def evaluate(self, quote: MarketQuote) -> RuleResult:
        return RuleResult(
            rule_name=self.name,
            symbol=quote.symbol,
            triggered=True,
            message="测试触发",
        )


def test_monitor_engine_isolates_rule_exception() -> None:
    quote = MarketQuote(
        instrument=MarketInstrument(
            code="000001",
            name="测试标的",
            type=InstrumentType.INDEX,
        ),
        timestamp=datetime.now(UTC),
        source="test",
        price=Decimal("10.00"),
        previous_close=Decimal("9.90"),
        open_price=Decimal("9.95"),
        high_price=Decimal("10.10"),
        low_price=Decimal("9.80"),
        volume=100_000,
        turnover=Decimal("1000000.00"),
    )
    engine = MonitorEngine([BrokenRule(), TriggerRule()])

    results = engine.evaluate([quote])

    assert len(results) == 1
    assert results[0].rule_name == "trigger"
