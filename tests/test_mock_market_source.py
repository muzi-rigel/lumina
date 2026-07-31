from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market.mock import MockMarketSource
from app.market.model import InstrumentType, MarketInstrument
from app.market.source import MarketSourceError

FIXED_TIME = datetime(2026, 7, 31, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _instruments() -> list[MarketInstrument]:
    return [
        MarketInstrument("510300", "沪深300ETF", InstrumentType.ETF),
        MarketInstrument("000001", "上证指数", InstrumentType.INDEX),
    ]


def test_mock_source_returns_deterministic_normalized_quotes() -> None:
    prices = {
        "510300": Decimal("4.000"),
        "000001": Decimal("3500.00"),
    }
    first_source = MockMarketSource(initial_prices=prices, clock=lambda: FIXED_TIME)
    second_source = MockMarketSource(initial_prices=prices, clock=lambda: FIXED_TIME)

    first_batch = first_source.fetch_quotes(_instruments())
    second_batch = second_source.fetch_quotes(_instruments())

    assert first_batch == second_batch
    assert first_batch.is_complete is True
    assert len(first_batch.quotes) == 2
    assert all(quote.source == "mock" for quote in first_batch.quotes)
    assert all(quote.timestamp == FIXED_TIME for quote in first_batch.quotes)


def test_mock_source_isolates_single_instrument_failure() -> None:
    source = MockMarketSource(
        failure_codes={"000001"},
        clock=lambda: FIXED_TIME,
    )

    batch = source.fetch_quotes(_instruments())

    assert [quote.symbol for quote in batch.quotes] == ["510300"]
    assert [failure.instrument.code for failure in batch.failures] == ["000001"]
    assert batch.failures[0].retryable is True
    assert batch.is_complete is False


def test_mock_source_rejects_naive_clock() -> None:
    source = MockMarketSource(clock=lambda: datetime(2026, 7, 31, 9, 30))

    with pytest.raises(MarketSourceError, match="必须返回带时区时间"):
        source.fetch_quotes(_instruments())


def test_mock_source_seed_reproduces_quote_sequence() -> None:
    first_source = MockMarketSource(seed=2026, clock=lambda: FIXED_TIME)
    second_source = MockMarketSource(seed=2026, clock=lambda: FIXED_TIME)

    first_sequence = [
        first_source.fetch_quotes(_instruments()),
        first_source.fetch_quotes(_instruments()),
    ]
    second_sequence = [
        second_source.fetch_quotes(_instruments()),
        second_source.fetch_quotes(_instruments()),
    ]

    assert first_sequence == second_sequence
