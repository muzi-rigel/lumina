from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.market.model import InstrumentType, MarketInstrument, MarketQuote


def _instrument() -> MarketInstrument:
    return MarketInstrument(
        code="510300",
        name="沪深300ETF",
        type=InstrumentType.ETF,
    )


def _quote(timestamp: datetime) -> MarketQuote:
    return MarketQuote(
        instrument=_instrument(),
        timestamp=timestamp,
        source="mock",
        price=Decimal("4.050"),
        previous_close=Decimal("4.000"),
        open_price=Decimal("4.010"),
        high_price=Decimal("4.060"),
        low_price=Decimal("3.990"),
        volume=1_000_000,
        turnover=Decimal("4050000.00"),
    )


def test_market_quote_exposes_derived_change() -> None:
    quote = _quote(datetime.now(UTC))

    assert quote.symbol == "510300"
    assert quote.name == "沪深300ETF"
    assert quote.change == Decimal("0.050")
    assert quote.change_percent == Decimal("1.2500")


def test_market_quote_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="必须包含时区"):
        _quote(datetime(2026, 7, 31, 9, 30))


def test_market_quote_rejects_float_price() -> None:
    with pytest.raises(TypeError, match="price 必须使用 Decimal"):
        MarketQuote(
            instrument=_instrument(),
            timestamp=datetime.now(UTC),
            source="mock",
            price=4.05,  # type: ignore[arg-type]
            previous_close=Decimal("4.000"),
            open_price=Decimal("4.010"),
            high_price=Decimal("4.060"),
            low_price=Decimal("3.990"),
            volume=1_000_000,
            turnover=Decimal("4050000.00"),
        )
