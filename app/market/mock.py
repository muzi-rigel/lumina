"""无网络依赖、结果可重复的 Mock 行情源。"""

from __future__ import annotations

import random
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.market.model import InstrumentType, MarketInstrument, MarketQuote
from app.market.source import MarketSource, MarketSourceError, QuoteBatch, QuoteFailure

PRICE_STEP = {
    InstrumentType.ETF: Decimal("0.001"),
    InstrumentType.INDEX: Decimal("0.01"),
    InstrumentType.STOCK: Decimal("0.01"),
}


class MockMarketSource(MarketSource):
    """生成确定性行情，并支持模拟指定代码失败。"""

    def __init__(
        self,
        initial_prices: Mapping[str, Decimal] | None = None,
        failure_codes: set[str] | None = None,
        clock: Callable[[], datetime] | None = None,
        seed: int | None = None,
    ) -> None:
        self._initial_prices = dict(initial_prices or {})
        self._failure_codes = frozenset(failure_codes or ())
        self._clock = clock or self._shanghai_now
        self._random = random.Random(0 if seed is None else seed)
        self._tick = 0
        self._lock = threading.Lock()
        self._validate_initial_prices()

    @property
    def name(self) -> str:
        return "mock"

    @staticmethod
    def _shanghai_now() -> datetime:
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _validate_initial_prices(self) -> None:
        for code, price in self._initial_prices.items():
            if len(code) != 6 or not code.isdigit():
                raise ValueError(f"Mock 初始价格代码非法：{code}")
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
                raise ValueError(f"Mock 初始价格非法：{code}")

    @staticmethod
    def _default_price(instrument: MarketInstrument) -> Decimal:
        suffix = Decimal(int(instrument.code[-3:])) / Decimal("100")
        if instrument.type is InstrumentType.INDEX:
            return Decimal("3000") + suffix
        if instrument.type is InstrumentType.ETF:
            return Decimal("3") + suffix / Decimal("100")
        return Decimal("10") + suffix

    def _build_quote(
        self,
        instrument: MarketInstrument,
        timestamp: datetime,
        tick: int,
        basis_points: int,
    ) -> MarketQuote:
        previous_close = self._initial_prices.get(
            instrument.code,
            self._default_price(instrument),
        )
        step = PRICE_STEP[instrument.type]
        movement = Decimal(basis_points)
        price = (previous_close * (Decimal("1") + movement / Decimal("1000"))).quantize(
            step,
            rounding=ROUND_HALF_UP,
        )
        edge = previous_close * Decimal("0.001")
        high_price = (max(previous_close, price) + edge).quantize(step, rounding=ROUND_HALF_UP)
        low_price = max(Decimal("0"), min(previous_close, price) - edge).quantize(
            step,
            rounding=ROUND_HALF_UP,
        )
        volume = 100_000 + tick * 1_000 + int(instrument.code[-3:])
        turnover = (price * volume).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return MarketQuote(
            instrument=instrument,
            timestamp=timestamp,
            source=self.name,
            price=price,
            previous_close=previous_close,
            open_price=previous_close,
            high_price=high_price,
            low_price=low_price,
            volume=volume,
            turnover=turnover,
        )

    def fetch_quotes(self, instruments: Sequence[MarketInstrument]) -> QuoteBatch:
        """生成一个批次；配置为失败的代码只进入 failures。"""

        timestamp = self._clock()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise MarketSourceError("Mock clock 必须返回带时区时间")

        with self._lock:
            self._tick += 1
            tick = self._tick
            movements = tuple(self._random.randint(-4, 4) for _ in instruments)

        quotes: list[MarketQuote] = []
        failures: list[QuoteFailure] = []
        for instrument, movement in zip(instruments, movements, strict=True):
            if instrument.code in self._failure_codes:
                failures.append(
                    QuoteFailure(
                        instrument=instrument,
                        message="Mock 模拟单标的失败",
                        retryable=True,
                    )
                )
                continue
            quotes.append(self._build_quote(instrument, timestamp, tick, movement))

        return QuoteBatch(
            source=self.name,
            requested_at=timestamp,
            quotes=tuple(quotes),
            failures=tuple(failures),
        )
