import logging
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market.model import MarketQuote
from app.monitor.engine import MonitorEngine
from app.monitor.history import QuoteHistory
from app.monitor.model import RuleDefinition, RuleEvaluation
from app.monitor.rules import MonitorRule, create_rule
from app.monitor.state import AlertStateStore
from tests.factories import make_quote, make_rule

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2026, 8, 8, 9, 30, tzinfo=TZ)


class BrokenRule(MonitorRule):
    def __init__(self, definition: RuleDefinition) -> None:
        super().__init__(definition)

    def evaluate(self, quote: MarketQuote, history: QuoteHistory) -> RuleEvaluation:
        del quote, history
        raise ValueError("模拟坏规则")


def _engine(*rules: MonitorRule) -> MonitorEngine:
    return MonitorEngine(rules, QuoteHistory(600, 200, TZ), AlertStateStore())


def test_monitor_engine_isolates_each_rule_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = BrokenRule(make_rule(rule_id="broken"))
    working = create_rule(make_rule(rule_id="working", threshold="1"))
    engine = _engine(broken, working)

    with caplog.at_level(logging.ERROR, logger="app.monitor.engine"):
        alerts = engine.evaluate(make_quote(START, price="10.1"))

    assert [alert.rule_id for alert in alerts] == ["working"]
    assert "rule_id=broken code=510300 error_type=ValueError reason=模拟坏规则" in caplog.text


def test_alert_contains_explainable_reference_data() -> None:
    engine = _engine(create_rule(make_rule(threshold="1")))

    alert = engine.evaluate(make_quote(START, price="10.1"))[0]

    assert alert.reference_price == Decimal("10")
    assert alert.reference_time is None
    assert alert.direction == make_rule().direction


def test_new_natural_date_resets_rule_state() -> None:
    engine = _engine(create_rule(make_rule(threshold="1", cooldown_seconds=86_400)))

    assert len(engine.evaluate(make_quote(START, price="10.1"))) == 1
    assert engine.evaluate(make_quote(START + timedelta(minutes=1), price="10.2")) == []
    next_day = START + timedelta(days=1)
    assert len(engine.evaluate(make_quote(next_day, price="10.1"))) == 1


def test_out_of_order_quote_is_not_evaluated() -> None:
    engine = _engine(create_rule(make_rule(threshold="1")))
    engine.evaluate(make_quote(START + timedelta(seconds=5), price="10"))

    assert engine.evaluate(make_quote(START, price="11")) == []
