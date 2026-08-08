"""MarketCollector 集成测试使用的可观察依赖。"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

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


def instrument(code: str, name: str) -> MarketInstrument:
    return MarketInstrument(code=code, name=name, type=InstrumentType.ETF)


def quote(value: MarketInstrument, source: str = "stub") -> MarketQuote:
    return MarketQuote(
        instrument=value,
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


def alert(value: MarketQuote, rule_id: str = "day-rise") -> AlertEvent:
    return AlertEvent(
        code=value.symbol,
        name=value.name,
        instrument_type=value.instrument.type,
        rule_id=rule_id,
        rule_name="日内上涨",
        rule_type=RuleType.DAY_CHANGE_PERCENT,
        direction=RuleDirection.RISE,
        severity=AlertSeverity.WARNING,
        triggered_at=value.timestamp,
        current_price=value.price,
        actual_change_percent=Decimal("1.25"),
        threshold=Decimal("1"),
        window_seconds=None,
        reference_price=value.previous_close,
        reference_time=None,
        message="测试告警",
    )


def batch(
    quotes: tuple[MarketQuote, ...],
    failures: tuple[QuoteFailure, ...] = (),
    source: str = "stub",
) -> QuoteBatch:
    return QuoteBatch(source, FIXED_TIME, quotes, failures)


class StubSource(MarketSource):
    def __init__(self, value: QuoteBatch) -> None:
        self._batch = value

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
        operations: list[str] | None = None,
    ) -> None:
        self.exploding_code = exploding_code
        self.alerts = alerts or []
        self.operations = operations
        self.received: list[MarketQuote] = []

    def evaluate(self, value: MarketQuote) -> list[AlertEvent]:
        if self.operations is not None:
            self.operations.append(f"evaluate:{value.symbol}")
        self.received.append(value)
        if value.symbol == self.exploding_code:
            raise RuntimeError("模拟监控引擎异常")
        return self.alerts


class RecordingRepository:
    def __init__(
        self,
        *,
        failing_quote_codes: frozenset[str] = frozenset(),
        failing_rule_ids: frozenset[str] = frozenset(),
        operations: list[str] | None = None,
    ) -> None:
        self.failing_quote_codes = failing_quote_codes
        self.failing_rule_ids = failing_rule_ids
        self.operations = operations
        self.quotes: list[MarketQuote] = []
        self.alerts: list[AlertEvent] = []

    def save_quote_snapshot(self, value: MarketQuote) -> None:
        if self.operations is not None:
            self.operations.append(f"save_quote:{value.symbol}")
        if value.symbol in self.failing_quote_codes:
            raise RuntimeError("模拟行情存储故障")
        self.quotes.append(value)

    def save_alert_event(self, value: AlertEvent) -> None:
        if self.operations is not None:
            self.operations.append(f"save_alert:{value.rule_id}")
        if value.rule_id in self.failing_rule_ids:
            raise RuntimeError("模拟告警存储故障")
        self.alerts.append(value)


class RecordingNotifier:
    def __init__(
        self,
        *,
        failing_rule_ids: frozenset[str] = frozenset(),
        operations: list[str] | None = None,
    ) -> None:
        self.failing_rule_ids = failing_rule_ids
        self.operations = operations
        self.alerts: list[AlertEvent] = []

    def send(self, value: AlertEvent) -> None:
        if self.operations is not None:
            self.operations.append(f"send:{value.rule_id}")
        if value.rule_id in self.failing_rule_ids:
            raise RuntimeError("模拟通知故障")
        self.alerts.append(value)
