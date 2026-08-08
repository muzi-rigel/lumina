from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market.model import InstrumentType
from app.monitor.history import QuoteHistory
from app.monitor.model import MatchStatus, RuleDirection, RuleTargets, RuleType
from app.monitor.rules import create_rule
from tests.factories import make_quote, make_rule

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2026, 8, 8, 9, 30, tzinfo=TZ)


def _history() -> QuoteHistory:
    return QuoteHistory(600, 200, TZ)


@pytest.mark.parametrize(
    ("direction", "price"),
    [
        (RuleDirection.RISE, "10.3"),
        (RuleDirection.FALL, "9.7"),
    ],
)
def test_day_change_triggers_at_equal_threshold(
    direction: RuleDirection,
    price: str,
) -> None:
    rule = create_rule(make_rule(direction=direction, threshold="3"))

    result = rule.evaluate(make_quote(START, price=price), _history())

    assert result.status is MatchStatus.MATCHED
    assert result.actual_change_percent in {Decimal("3.00"), Decimal("-3.00")}
    assert result.reference_price == Decimal("10")
    assert result.reference_time is None


def test_day_change_preserves_decimal_precision() -> None:
    rule = create_rule(make_rule(threshold="0.3333333333333333333333333333"))
    quote = make_quote(START, price="3.01", previous_close="3")

    result = rule.evaluate(quote, _history())

    assert result.status is MatchStatus.MATCHED
    assert result.actual_change_percent == Decimal("0.3333333333333333333333333333")


def test_day_change_with_invalid_previous_close_is_unknown() -> None:
    rule = create_rule(make_rule())

    result = rule.evaluate(make_quote(START, price="1", previous_close="0"), _history())

    assert result.status is MatchStatus.UNKNOWN


def test_non_applicable_target_does_not_apply() -> None:
    definition = make_rule(targets=RuleTargets(codes=frozenset({"000001"})))

    assert create_rule(definition).applies_to(make_quote(START)) is False


@pytest.mark.parametrize(
    ("direction", "current_price"),
    [
        (RuleDirection.RISE, "11.5"),
        (RuleDirection.FALL, "8.5"),
    ],
)
def test_window_change_triggers_in_both_directions(
    direction: RuleDirection,
    current_price: str,
) -> None:
    history = _history()
    baseline = make_quote(START, price="10")
    current = make_quote(START + timedelta(seconds=300), price=current_price)
    history.add(baseline)
    history.add(current)
    rule = create_rule(
        make_rule(
            rule_type=RuleType.WINDOW_CHANGE_PERCENT,
            direction=direction,
            threshold="15",
            window_seconds=300,
        )
    )

    result = rule.evaluate(current, history)

    assert result.status is MatchStatus.MATCHED
    assert result.reference_price == Decimal("10")
    assert result.reference_time == START


def test_window_history_shortage_is_unknown() -> None:
    history = _history()
    current = make_quote(START + timedelta(seconds=300))
    history.add(current)
    rule = create_rule(make_rule(rule_type=RuleType.WINDOW_CHANGE_PERCENT, window_seconds=300))

    assert rule.evaluate(current, history).status is MatchStatus.UNKNOWN


def test_window_invalid_baseline_price_is_unknown() -> None:
    history = _history()
    baseline = make_quote(START, price="0", previous_close="0")
    current = make_quote(START + timedelta(seconds=300), price="1")
    history.add(baseline)
    history.add(current)
    rule = create_rule(make_rule(rule_type=RuleType.WINDOW_CHANGE_PERCENT, window_seconds=300))

    assert rule.evaluate(current, history).status is MatchStatus.UNKNOWN


def test_target_type_applies_only_to_matching_instrument() -> None:
    targets = RuleTargets(instrument_types=frozenset({InstrumentType.INDEX}))
    rule = create_rule(make_rule(targets=targets))

    assert rule.applies_to(make_quote(START)) is False
