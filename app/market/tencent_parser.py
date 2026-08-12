"""腾讯行情文本到统一 MarketQuote 的严格解析。

当前支持的腾讯 ``~`` 分隔字段索引：

- 2：证券代码
- 3：当前价
- 4：昨收价
- 5：开盘价
- 6：累计成交量（供应方原始整数，单位暂未统一）
- 30：行情时间，格式为 ``YYYYmmddHHMMSS``
- 33：最高价
- 34：最低价
- 37：成交额（供应方原始 Decimal，单位暂未统一）

成交量和成交额不做推测性单位换算，待不同标的类型的单位得到验证后再统一。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.market.model import MarketInstrument, MarketQuote
from app.market.source import QuoteFailure
from app.market.symbols import SymbolMappingError, to_tencent_symbol

ENTRY_PATTERN = re.compile(r'v_((?:sh|sz)\d{6})="([^"]*)";')
SHANGHAI = ZoneInfo("Asia/Shanghai")
MIN_FIELD_COUNT = 38
CODE_INDEX = 2
PRICE_INDEX = 3
PREVIOUS_CLOSE_INDEX = 4
OPEN_PRICE_INDEX = 5
VOLUME_INDEX = 6
TIMESTAMP_INDEX = 30
HIGH_PRICE_INDEX = 33
LOW_PRICE_INDEX = 34
TURNOVER_INDEX = 37


class TencentResponseError(ValueError):
    """整个腾讯响应的外层结构无法安全解析。"""


@dataclass(frozen=True, slots=True)
class TencentParseResult:
    quotes: tuple[MarketQuote, ...]
    failures: tuple[QuoteFailure, ...]


def _decimal(fields: list[str], index: int, name: str) -> Decimal:
    try:
        value = Decimal(fields[index])
    except (IndexError, InvalidOperation) as exc:
        raise ValueError(f"字段 {name} 不是有效 Decimal") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"字段 {name} 必须是非负有限数值")
    return value


def _raw_volume(fields: list[str]) -> int:
    volume = _decimal(fields, VOLUME_INDEX, "volume")
    if volume != volume.to_integral_value():
        raise ValueError("字段 volume 必须是整数")
    return int(volume)


def _quote_time(fields: list[str]) -> datetime:
    try:
        return datetime.strptime(fields[TIMESTAMP_INDEX], "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
    except (IndexError, ValueError) as exc:
        raise ValueError("字段 quote_time 格式非法") from exc


def _parse_quote(
    instrument: MarketInstrument,
    fields: list[str],
) -> MarketQuote:
    if len(fields) < MIN_FIELD_COUNT:
        raise ValueError(f"字段数量不足，至少需要 {MIN_FIELD_COUNT} 个")
    if fields[CODE_INDEX] != instrument.code:
        raise ValueError("返回证券代码与请求不一致")

    price = _decimal(fields, PRICE_INDEX, "price")
    previous_close = _decimal(fields, PREVIOUS_CLOSE_INDEX, "previous_close")
    if price <= 0 or previous_close <= 0:
        raise ValueError("当前价和昨收必须大于 0")
    return MarketQuote(
        instrument=instrument,
        timestamp=_quote_time(fields),
        source="tencent",
        price=price,
        previous_close=previous_close,
        open_price=_decimal(fields, OPEN_PRICE_INDEX, "open_price"),
        high_price=_decimal(fields, HIGH_PRICE_INDEX, "high_price"),
        low_price=_decimal(fields, LOW_PRICE_INDEX, "low_price"),
        volume=_raw_volume(fields),
        turnover=_decimal(fields, TURNOVER_INDEX, "turnover"),
    )


class TencentQuoteParser:
    """按请求标的隔离单条解析错误，拒绝损坏的响应外壳。"""

    def parse(
        self,
        response_text: str,
        instruments: tuple[MarketInstrument, ...],
    ) -> TencentParseResult:
        matches = tuple(ENTRY_PATTERN.finditer(response_text))
        if not matches or ENTRY_PATTERN.sub("", response_text).strip():
            raise TencentResponseError("腾讯行情响应结构非法")

        requested: dict[str, MarketInstrument] = {}
        failures: list[QuoteFailure] = []
        for instrument in instruments:
            try:
                requested[to_tencent_symbol(instrument)] = instrument
            except SymbolMappingError as exc:
                failures.append(QuoteFailure(instrument, str(exc), retryable=False))

        entries: dict[str, list[str]] = {}
        duplicate_symbols: set[str] = set()
        for match in matches:
            symbol = match.group(1)
            if symbol not in requested:
                raise TencentResponseError("腾讯响应包含未请求的证券代码")
            if symbol in entries:
                duplicate_symbols.add(symbol)
            entries[symbol] = match.group(2).split("~")

        quotes: list[MarketQuote] = []
        for symbol, instrument in requested.items():
            if symbol in duplicate_symbols:
                failures.append(QuoteFailure(instrument, "腾讯响应包含重复记录", retryable=True))
                continue
            fields = entries.get(symbol)
            if fields is None:
                failures.append(QuoteFailure(instrument, "腾讯响应缺少该标的", retryable=True))
                continue
            try:
                quotes.append(_parse_quote(instrument, fields))
            except (TypeError, ValueError) as exc:
                failures.append(
                    QuoteFailure(
                        instrument,
                        f"腾讯行情解析失败：{type(exc).__name__} {exc}",
                        retryable=True,
                    )
                )
        return TencentParseResult(tuple(quotes), tuple(failures))
