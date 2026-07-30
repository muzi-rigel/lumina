from datetime import UTC, datetime
from decimal import Decimal

from app.market.source import MarketQuote
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
        symbol="000001",
        name="测试标的",
        price=Decimal("10.00"),
        timestamp=datetime.now(UTC),
        source="test",
    )
    engine = MonitorEngine([BrokenRule(), TriggerRule()])

    results = engine.evaluate([quote])

    assert len(results) == 1
    assert results[0].rule_name == "trigger"
