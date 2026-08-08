import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market.collector import MarketCollector
from app.market.model import InstrumentType, MarketInstrument, MarketQuote
from app.market.source import MarketSource, MarketSourceError, QuoteBatch, QuoteFailure
from app.monitor.engine import MonitorEngine
from app.monitor.model import (
    AlertEvent,
    AlertSeverity,
    RuleDirection,
    RuleType,
)

FIXED_TIME = datetime(2026, 7, 31, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _instrument(code: str, name: str) -> MarketInstrument:
    return MarketInstrument(code=code, name=name, type=InstrumentType.ETF)


def _quote(instrument: MarketInstrument, source: str = "stub") -> MarketQuote:
    return MarketQuote(
        instrument=instrument,
        timestamp=FIXED_TIME,
        source=source,
        price=Decimal("4.050"),
        previous_close=Decimal("4.000"),
        open_price=Decimal("4.010"),
        high_price=Decimal("4.060"),
        low_price=Decimal("3.990"),
        volume=100_000,
        turnover=Decimal("405000.00"),
    )


class StubSource(MarketSource):
    def __init__(self, batch: QuoteBatch) -> None:
        self._batch = batch

    @property
    def name(self) -> str:
        return "stub"

    def fetch_quotes(self, instruments: Sequence[MarketInstrument]) -> QuoteBatch:
        del instruments
        return self._batch


class FlakySource(MarketSource):
    def __init__(self, success_batch: QuoteBatch) -> None:
        self._success_batch = success_batch
        self.calls = 0

    @property
    def name(self) -> str:
        return "flaky"

    def fetch_quotes(self, instruments: Sequence[MarketInstrument]) -> QuoteBatch:
        del instruments
        self.calls += 1
        if self.calls == 1:
            raise MarketSourceError("模拟系统级故障")
        return self._success_batch


class RecordingMonitorEngine(MonitorEngine):
    def __init__(
        self,
        exploding_code: str | None = None,
        alerts: list[AlertEvent] | None = None,
    ) -> None:
        self.exploding_code = exploding_code
        self.alerts = alerts or []
        self.received: list[MarketQuote] = []

    def evaluate(self, quote: MarketQuote) -> list[AlertEvent]:
        self.received.append(quote)
        if quote.symbol == self.exploding_code:
            raise RuntimeError("模拟监控引擎异常")
        return self.alerts


def _alert(quote: MarketQuote) -> AlertEvent:
    return AlertEvent(
        code=quote.symbol,
        name=quote.name,
        instrument_type=quote.instrument.type,
        rule_id="day-rise",
        rule_name="日内上涨",
        rule_type=RuleType.DAY_CHANGE_PERCENT,
        direction=RuleDirection.RISE,
        severity=AlertSeverity.WARNING,
        triggered_at=quote.timestamp,
        current_price=quote.price,
        actual_change_percent=Decimal("1.25"),
        threshold=Decimal("1"),
        window_seconds=None,
        reference_price=quote.previous_close,
        reference_time=None,
        message="测试告警",
    )


def _batch(
    quotes: tuple[MarketQuote, ...],
    failures: tuple[QuoteFailure, ...] = (),
    source: str = "stub",
) -> QuoteBatch:
    return QuoteBatch(
        source=source,
        requested_at=FIXED_TIME,
        quotes=quotes,
        failures=failures,
    )


def test_collector_processes_normal_batch_with_unified_quote(
    caplog: pytest.LogCaptureFixture,
) -> None:
    instrument = _instrument("510300", "沪深300ETF")
    quote = _quote(instrument)
    engine = RecordingMonitorEngine()
    collector = MarketCollector(StubSource(_batch((quote,))), [instrument], engine)

    with caplog.at_level(logging.INFO, logger="app.market.collector"):
        batch = collector.collect_once()

    assert batch is not None
    assert engine.received == [quote]
    assert isinstance(engine.received[0], MarketQuote)
    assert "行情成功 code=510300 name=沪深300ETF" in caplog.text
    assert "price=4.050 change=0.050 change_pct=1.2500%" in caplog.text


def test_partial_failure_does_not_drop_success(caplog: pytest.LogCaptureFixture) -> None:
    success = _instrument("510300", "沪深300ETF")
    failed = _instrument("512480", "半导体ETF")
    quote = _quote(success)
    failure = QuoteFailure(failed, "模拟失败", retryable=True)
    engine = RecordingMonitorEngine()
    collector = MarketCollector(
        StubSource(_batch((quote,), (failure,))),
        [success, failed],
        engine,
    )

    with caplog.at_level(logging.WARNING, logger="app.market.collector"):
        collector.collect_once()

    assert engine.received == [quote]
    assert "行情失败 code=512480 reason=模拟失败" in caplog.text


def test_monitor_exception_isolated_per_quote(caplog: pytest.LogCaptureFixture) -> None:
    first = _instrument("510300", "沪深300ETF")
    second = _instrument("512480", "半导体ETF")
    engine = RecordingMonitorEngine(exploding_code=first.code)
    collector = MarketCollector(
        StubSource(_batch((_quote(first), _quote(second)))),
        [first, second],
        engine,
    )

    with caplog.at_level(logging.ERROR, logger="app.market.collector"):
        collector.collect_once()

    assert [quote.symbol for quote in engine.received] == [first.code, second.code]
    assert "行情处理异常 code=510300" in caplog.text
    assert "error_type=RuntimeError reason=模拟监控引擎异常" in caplog.text


def test_collector_logs_alert_event(caplog: pytest.LogCaptureFixture) -> None:
    instrument = _instrument("510300", "沪深300ETF")
    quote = _quote(instrument)
    engine = RecordingMonitorEngine(alerts=[_alert(quote)])
    collector = MarketCollector(StubSource(_batch((quote,))), [instrument], engine)

    with caplog.at_level(logging.WARNING, logger="app.market.collector"):
        collector.collect_once()

    assert "alert rule_id=day-rise code=510300 name=沪深300ETF" in caplog.text
    assert "actual_change_pct=1.2500 threshold=1.0000" in caplog.text
    assert "reference_price=4.000 reference_time=N/A" in caplog.text


def test_market_source_error_only_ends_current_cycle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    instrument = _instrument("510300", "沪深300ETF")
    engine = RecordingMonitorEngine()
    source = FlakySource(_batch((_quote(instrument, source="flaky"),), source="flaky"))
    collector = MarketCollector(source, [instrument], engine)

    with caplog.at_level(logging.ERROR, logger="app.market.collector"):
        first_result = collector.collect_once()
        second_result = collector.collect_once()

    assert first_result is None
    assert second_result is not None
    assert engine.received == [_quote(instrument, source="flaky")]
    assert "行情源故障 source=flaky" in caplog.text
