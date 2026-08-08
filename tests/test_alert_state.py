from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.monitor.model import MatchStatus
from app.monitor.state import AlertStateStore

NOW = datetime(2026, 8, 8, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def _observe(
    store: AlertStateStore,
    status: MatchStatus,
    seconds: int,
    *,
    code: str = "510300",
    rule_id: str = "rule-a",
    cooldown: int = 60,
) -> bool:
    return store.should_trigger(
        code=code,
        rule_id=rule_id,
        status=status,
        observed_at=NOW + timedelta(seconds=seconds),
        cooldown_seconds=cooldown,
    )


def test_first_match_triggers_but_continuous_match_does_not() -> None:
    store = AlertStateStore()

    assert _observe(store, MatchStatus.MATCHED, 0) is True
    assert _observe(store, MatchStatus.MATCHED, 10) is False


def test_not_matched_rearms_rule() -> None:
    store = AlertStateStore()
    assert _observe(store, MatchStatus.MATCHED, 0) is True
    assert _observe(store, MatchStatus.NOT_MATCHED, 10) is False

    assert _observe(store, MatchStatus.MATCHED, 61) is True


def test_cooldown_suppression_has_no_delayed_trigger() -> None:
    store = AlertStateStore()
    assert _observe(store, MatchStatus.MATCHED, 0) is True
    assert _observe(store, MatchStatus.NOT_MATCHED, 10) is False
    assert _observe(store, MatchStatus.MATCHED, 20) is False

    # 冷却结束时仍持续满足，不能补发之前被抑制的突破。
    assert _observe(store, MatchStatus.MATCHED, 70) is False
    assert _observe(store, MatchStatus.NOT_MATCHED, 71) is False
    assert _observe(store, MatchStatus.MATCHED, 72) is True


def test_unknown_neither_rearms_nor_changes_match_state() -> None:
    store = AlertStateStore()
    assert _observe(store, MatchStatus.MATCHED, 0) is True
    assert _observe(store, MatchStatus.UNKNOWN, 10) is False

    assert _observe(store, MatchStatus.MATCHED, 70) is False


def test_time_rollback_cannot_bypass_cooldown() -> None:
    store = AlertStateStore()
    assert _observe(store, MatchStatus.MATCHED, 60) is True
    assert _observe(store, MatchStatus.NOT_MATCHED, 70) is False

    assert _observe(store, MatchStatus.MATCHED, 30) is False


def test_code_and_rule_state_are_isolated() -> None:
    store = AlertStateStore()
    assert _observe(store, MatchStatus.MATCHED, 0) is True

    assert _observe(store, MatchStatus.MATCHED, 0, code="512480") is True
    assert _observe(store, MatchStatus.MATCHED, 0, rule_id="rule-b") is True
