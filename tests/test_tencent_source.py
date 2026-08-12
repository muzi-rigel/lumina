from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.core.market_config import TencentSettings
from app.market.model import InstrumentType, MarketInstrument
from app.market.source import MarketSourceError
from app.market.tencent import TencentMarketSource
from app.market.tencent_http import MAX_TENCENT_RESPONSE_BYTES, TencentHttpResult
from app.market.tencent_parser import TencentParseResult, TencentQuoteParser
from tests.factories import make_quote

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 8, 10, 0, 5, tzinfo=TZ)
FIXTURE = Path("tests/fixtures/tencent_quotes.txt")


class ScriptedTransport:
    def __init__(self, outcomes: Sequence[TencentHttpResult | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, timeout: float) -> TencentHttpResult:
        self.calls.append((url, timeout))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class EmptyParser(TencentQuoteParser):
    def parse(
        self,
        response_text: str,
        instruments: tuple[MarketInstrument, ...],
    ) -> TencentParseResult:
        del response_text, instruments
        return TencentParseResult((), ())


class FutureParser(TencentQuoteParser):
    def parse(
        self,
        response_text: str,
        instruments: tuple[MarketInstrument, ...],
    ) -> TencentParseResult:
        del response_text
        quote = make_quote(NOW + timedelta(minutes=1), code=instruments[0].code)
        return TencentParseResult((quote,), ())


def _settings(attempts: int = 2) -> TencentSettings:
    return TencentSettings(
        url="https://qt.gtimg.cn/q=",
        timeout_seconds=3,
        batch_size=50,
        max_attempts=attempts,
        retry_backoff_seconds=0,
        max_total_seconds=8,
    )


def _instruments() -> tuple[MarketInstrument, ...]:
    return (
        MarketInstrument("510300", "沪深300ETF", InstrumentType.ETF),
        MarketInstrument("000001", "上证指数", InstrumentType.INDEX),
        MarketInstrument("000001", "平安银行", InstrumentType.STOCK),
    )


def _result(body: bytes, status: int = 200) -> TencentHttpResult:
    return TencentHttpResult(status, body)


def test_source_fetches_realistic_offline_fixture() -> None:
    body = FIXTURE.read_bytes()
    transport = ScriptedTransport([_result(body)])
    source = TencentMarketSource(_settings(), transport=transport, clock=lambda: NOW)

    batch = source.fetch_quotes(_instruments())

    assert batch.source == "tencent"
    assert batch.requested_at == NOW
    assert len(batch.quotes) == 3
    assert batch.failures == ()
    assert transport.calls[0][0].endswith("q=sh510300,sh000001,sz000001")


@pytest.mark.parametrize("first", [TimeoutError("timeout"), _result(b"", 503)])
def test_source_retries_transient_transport_failure(
    first: TencentHttpResult | Exception,
) -> None:
    line = FIXTURE.read_bytes().splitlines()[0]
    transport = ScriptedTransport([first, _result(line)])
    source = TencentMarketSource(_settings(), transport=transport, clock=lambda: NOW)

    batch = source.fetch_quotes(_instruments()[:1])

    assert len(batch.quotes) == 1
    assert len(transport.calls) == 2


def test_source_does_not_retry_permanent_http_error() -> None:
    transport = ScriptedTransport([_result(b"bad request", 400)])
    source = TencentMarketSource(_settings(), transport=transport, clock=lambda: NOW)

    with pytest.raises(MarketSourceError, match="HTTP 响应异常：400"):
        source.fetch_quotes(_instruments()[:1])

    assert len(transport.calls) == 1


def test_source_retries_invalid_encoding_then_fails_cycle() -> None:
    transport = ScriptedTransport([_result(b"\xff"), _result(b"\xff")])
    source = TencentMarketSource(_settings(), transport=transport, clock=lambda: NOW)

    with pytest.raises(MarketSourceError, match="响应无效"):
        source.fetch_quotes(_instruments()[:1])

    assert len(transport.calls) == 2


def test_source_rejects_empty_response_as_market_source_error() -> None:
    source = TencentMarketSource(
        _settings(attempts=1),
        transport=ScriptedTransport([_result(b"")]),
        clock=lambda: NOW,
    )

    with pytest.raises(MarketSourceError, match="响应无效"):
        source.fetch_quotes(_instruments()[:1])


def test_source_rejects_invalid_response_format_as_market_source_error() -> None:
    source = TencentMarketSource(
        _settings(attempts=1),
        transport=ScriptedTransport([_result(b"not a tencent response")]),
        clock=lambda: NOW,
    )

    with pytest.raises(MarketSourceError, match="响应无效"):
        source.fetch_quotes(_instruments()[:1])


def test_source_rejects_response_over_size_limit() -> None:
    source = TencentMarketSource(
        _settings(attempts=1),
        transport=ScriptedTransport([_result(b"x" * (MAX_TENCENT_RESPONSE_BYTES + 1))]),
        clock=lambda: NOW,
    )

    with pytest.raises(MarketSourceError, match="超过大小限制"):
        source.fetch_quotes(_instruments()[:1])


def test_source_keeps_other_quotes_when_one_security_cannot_be_parsed() -> None:
    lines = FIXTURE.read_bytes().splitlines()[:2]
    lines[0] = lines[0].replace(b"~4.120~4.100~", b"~invalid~4.100~")
    source = TencentMarketSource(
        _settings(),
        transport=ScriptedTransport([_result(b"\n".join(lines))]),
        clock=lambda: NOW,
    )

    batch = source.fetch_quotes(_instruments()[:2])

    assert [quote.instrument for quote in batch.quotes] == [_instruments()[1]]
    assert [failure.instrument for failure in batch.failures] == [_instruments()[0]]
    assert batch.failures[0].retryable is True


def test_source_total_budget_prevents_unbounded_backoff() -> None:
    settings = TencentSettings(
        url="https://qt.gtimg.cn/q=",
        timeout_seconds=3,
        batch_size=50,
        max_attempts=2,
        retry_backoff_seconds=5,
        max_total_seconds=2,
    )
    transport = ScriptedTransport([_result(b"", 503)])
    source = TencentMarketSource(settings, transport=transport, clock=lambda: NOW)

    with pytest.raises(MarketSourceError, match="最大总耗时"):
        source.fetch_quotes(_instruments()[:1])

    assert len(transport.calls) == 1
    assert transport.calls[0][1] <= 2


def test_source_isolates_unmappable_instrument() -> None:
    valid = _instruments()[0]
    unsupported = MarketInstrument("430047", "北交所测试", InstrumentType.STOCK)
    line = FIXTURE.read_bytes().splitlines()[0]
    source = TencentMarketSource(
        _settings(),
        transport=ScriptedTransport([_result(line)]),
        clock=lambda: NOW,
    )

    batch = source.fetch_quotes((valid, unsupported))

    assert [quote.instrument for quote in batch.quotes] == [valid]
    assert [failure.instrument for failure in batch.failures] == [unsupported]
    assert batch.failures[0].retryable is False


def test_source_splits_large_batches_without_threads() -> None:
    instruments = tuple(
        MarketInstrument(f"6{index:05d}", f"测试{index}", InstrumentType.STOCK)
        for index in range(51)
    )
    transport = ScriptedTransport([_result(b"ok"), _result(b"ok")])
    source = TencentMarketSource(
        _settings(),
        transport=transport,
        parser=EmptyParser(),
        clock=lambda: NOW,
    )

    batch = source.fetch_quotes(instruments)

    assert batch.quotes == ()
    assert len(transport.calls) == 2
    assert transport.calls[0][0].count(",") == 49
    assert transport.calls[1][0].count(",") == 0


def test_source_raises_when_later_http_chunk_fails() -> None:
    instruments = tuple(
        MarketInstrument(f"6{index:05d}", f"测试{index}", InstrumentType.STOCK)
        for index in range(51)
    )
    transport = ScriptedTransport([_result(b"ok"), _result(b"", 503), _result(b"", 503)])
    source = TencentMarketSource(
        _settings(),
        transport=transport,
        parser=EmptyParser(),
        clock=lambda: NOW,
    )

    with pytest.raises(MarketSourceError, match="HTTP 响应异常：503"):
        source.fetch_quotes(instruments)


def test_source_rejects_future_provider_timestamp() -> None:
    instrument = _instruments()[0]
    source = TencentMarketSource(
        _settings(),
        transport=ScriptedTransport([_result(b"ok")]),
        parser=FutureParser(),
        clock=lambda: NOW,
    )

    batch = source.fetch_quotes((instrument,))

    assert batch.quotes == ()
    assert "晚于本机时间" in batch.failures[0].message


def test_source_rejects_naive_clock() -> None:
    source = TencentMarketSource(
        _settings(),
        transport=ScriptedTransport([]),
        clock=lambda: datetime(2026, 8, 8, 10, 0),
    )

    with pytest.raises(MarketSourceError, match="clock"):
        source.fetch_quotes(_instruments())
