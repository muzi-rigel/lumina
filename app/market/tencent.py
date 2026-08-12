"""腾讯 A 股行情源。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from urllib.error import URLError
from zoneinfo import ZoneInfo

from app.core.market_config import TencentSettings
from app.core.retry import RetryBudgetExceeded, RetryController, RetryPolicy
from app.market.model import MarketInstrument, MarketQuote
from app.market.source import MarketSource, MarketSourceError, QuoteBatch, QuoteFailure
from app.market.symbols import SymbolMappingError, to_tencent_symbol
from app.market.tencent_http import (
    MAX_TENCENT_RESPONSE_BYTES,
    TencentHttpTransport,
    UrllibTencentHttpTransport,
)
from app.market.tencent_parser import (
    TencentParseResult,
    TencentQuoteParser,
    TencentResponseError,
)

MAX_FUTURE_SKEW = timedelta(seconds=30)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class TencentMarketSource(MarketSource):
    """批量请求腾讯行情，并按标的隔离映射和解析错误。"""

    def __init__(
        self,
        settings: TencentSettings,
        transport: TencentHttpTransport | None = None,
        parser: TencentQuoteParser | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport or UrllibTencentHttpTransport()
        self._parser = parser or TencentQuoteParser()
        self._clock = clock or (lambda: datetime.now(SHANGHAI))
        self._policy = RetryPolicy(
            settings.max_attempts,
            settings.retry_backoff_seconds,
            settings.max_total_seconds,
        )

    @property
    def name(self) -> str:
        return "tencent"

    def _url(self, instruments: tuple[MarketInstrument, ...]) -> str:
        symbols = ",".join(to_tencent_symbol(instrument) for instrument in instruments)
        return f"{self._settings.url}{symbols}"

    def _fetch_chunk(self, instruments: tuple[MarketInstrument, ...]) -> TencentParseResult:
        last_error = MarketSourceError("腾讯行情请求未执行")
        controller = RetryController(self._policy, self._settings.timeout_seconds)
        try:
            for attempt in controller:
                try:
                    result = self._transport.get(
                        self._url(instruments),
                        timeout=attempt.timeout_seconds,
                    )
                except (OSError, TimeoutError, URLError) as exc:
                    last_error = MarketSourceError(f"腾讯行情网络失败：{type(exc).__name__}")
                    continue

                if result.status_code == 429 or result.status_code >= 500:
                    last_error = MarketSourceError(f"腾讯行情 HTTP 响应异常：{result.status_code}")
                    continue
                if not 200 <= result.status_code < 300:
                    raise MarketSourceError(f"腾讯行情 HTTP 响应异常：{result.status_code}")
                if len(result.body) > MAX_TENCENT_RESPONSE_BYTES:
                    last_error = MarketSourceError("腾讯行情响应超过大小限制")
                    continue
                try:
                    response_text = result.body.decode("gb18030")
                    return self._parser.parse(response_text, instruments)
                except (UnicodeDecodeError, TencentResponseError) as exc:
                    last_error = MarketSourceError(f"腾讯行情响应无效：{type(exc).__name__}")
        except RetryBudgetExceeded as exc:
            raise MarketSourceError("腾讯行情请求超过最大总耗时") from exc
        raise last_error

    def _chunks(
        self,
        instruments: tuple[MarketInstrument, ...],
    ) -> tuple[tuple[MarketInstrument, ...], ...]:
        return tuple(
            instruments[index : index + self._settings.batch_size]
            for index in range(0, len(instruments), self._settings.batch_size)
        )

    @staticmethod
    def _filter_future_quotes(
        result: TencentParseResult,
        requested_at: datetime,
    ) -> TencentParseResult:
        quotes: list[MarketQuote] = []
        failures = list(result.failures)
        future_limit = requested_at + MAX_FUTURE_SKEW
        for quote in result.quotes:
            if quote.timestamp > future_limit:
                failures.append(
                    QuoteFailure(quote.instrument, "腾讯行情时间明显晚于本机时间", retryable=True)
                )
            else:
                quotes.append(quote)
        return TencentParseResult(tuple(quotes), tuple(failures))

    def fetch_quotes(self, instruments: Sequence[MarketInstrument]) -> QuoteBatch:
        requested_at = self._clock()
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise MarketSourceError("腾讯行情 clock 必须返回带时区时间")

        valid: list[MarketInstrument] = []
        failures: list[QuoteFailure] = []
        for instrument in instruments:
            try:
                to_tencent_symbol(instrument)
                valid.append(instrument)
            except SymbolMappingError as exc:
                failures.append(QuoteFailure(instrument, str(exc), retryable=False))

        quotes: list[MarketQuote] = []
        chunks = self._chunks(tuple(valid))
        for chunk in chunks:
            result = self._filter_future_quotes(
                self._fetch_chunk(chunk),
                requested_at,
            )
            quotes.extend(result.quotes)
            failures.extend(result.failures)

        return QuoteBatch(self.name, requested_at, tuple(quotes), tuple(failures))
