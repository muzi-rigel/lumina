from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.market.model import InstrumentType
from app.monitor.history import HistoryUpdateStatus, QuoteHistory
from tests.factories import make_quote

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2026, 8, 8, 9, 30, tzinfo=TZ)


def _history(max_points: int = 20) -> QuoteHistory:
    return QuoteHistory(600, max_points, TZ)


def test_histories_are_isolated_by_code() -> None:
    history = _history()
    history.add(make_quote(START, code="510300"))
    history.add(make_quote(START, code="000001", instrument_type=InstrumentType.INDEX))

    assert history.size("510300") == 1
    assert history.size("000001") == 1


def test_maxlen_is_an_abnormal_sampling_guard() -> None:
    history = _history(max_points=3)
    for offset in range(5):
        history.add(make_quote(START + timedelta(seconds=offset)))

    assert history.size("510300") == 3


def test_baseline_requires_sufficient_history() -> None:
    history = _history()
    current = make_quote(START + timedelta(seconds=60), price="11")
    history.add(current)

    assert history.baseline(current.symbol, current.timestamp, 60) is None


def test_baseline_uses_exact_boundary_match() -> None:
    history = _history()
    baseline = make_quote(START, price="10")
    current = make_quote(START + timedelta(seconds=60), price="11")
    history.add(baseline)
    history.add(current)

    assert history.baseline(current.symbol, current.timestamp, 60) == baseline


def test_baseline_uses_latest_quote_not_after_boundary() -> None:
    history = _history()
    older = make_quote(START + timedelta(seconds=5), price="10")
    closest = make_quote(START + timedelta(seconds=9), price="10.1")
    after = make_quote(START + timedelta(seconds=11), price="10.2")
    current = make_quote(START + timedelta(seconds=70), price="11")
    for quote in (older, closest, after, current):
        history.add(quote)

    assert history.baseline(current.symbol, current.timestamp, 60) == closest


def test_new_natural_date_clears_old_history() -> None:
    history = _history()
    history.add(make_quote(START))
    next_day = make_quote(START + timedelta(days=1))

    result = history.add(next_day)

    assert result.date_changed is True
    assert history.size(next_day.symbol) == 1
    assert history.baseline(next_day.symbol, next_day.timestamp, 60) is None


def test_out_of_order_quote_does_not_pollute_history() -> None:
    history = _history()
    latest = make_quote(START + timedelta(seconds=10), price="11")
    history.add(latest)

    result = history.add(make_quote(START, price="9"))

    assert result.status is HistoryUpdateStatus.OUT_OF_ORDER
    assert history.size(latest.symbol) == 1


def test_duplicate_timestamp_uses_last_write_wins() -> None:
    history = _history()
    history.add(make_quote(START, price="10"))
    replacement = make_quote(START, price="12")

    result = history.add(replacement)

    assert result.status is HistoryUpdateStatus.REPLACED
    assert history.size(replacement.symbol) == 1
    current = make_quote(START + timedelta(seconds=60), price="13")
    history.add(current)
    assert history.baseline(current.symbol, current.timestamp, 60) == replacement
