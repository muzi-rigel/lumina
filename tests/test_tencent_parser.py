from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.market.model import InstrumentType, MarketInstrument
from app.market.tencent_parser import TencentQuoteParser, TencentResponseError

FIXTURE = Path("tests/fixtures/tencent_real_quotes.txt")
CODE_INDEX = 2
PRICE_INDEX = 3
PREVIOUS_CLOSE_INDEX = 4
TIMESTAMP_INDEX = 30


def _instruments() -> tuple[MarketInstrument, ...]:
    return (
        MarketInstrument("510300", "配置ETF名称", InstrumentType.ETF),
        MarketInstrument("000001", "上证指数", InstrumentType.INDEX),
        MarketInstrument("000001", "平安银行", InstrumentType.STOCK),
    )


def _fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _replace_field(line: str, index: int, value: str) -> str:
    prefix, raw_fields = line.split('="', maxsplit=1)
    fields = raw_fields.removesuffix('";').split("~")
    fields[index] = value
    payload = "~".join(fields)
    return f'{prefix}="{payload}";'


def _truncate_fields(line: str, count: int) -> str:
    prefix, raw_fields = line.split('="', maxsplit=1)
    fields = raw_fields.removesuffix('";').split("~")[:count]
    payload = "~".join(fields)
    return f'{prefix}="{payload}";'


def test_parser_builds_decimal_quotes_without_guessing_provider_units() -> None:
    result = TencentQuoteParser().parse(_fixture(), _instruments())

    assert result.failures == ()
    assert [quote.symbol for quote in result.quotes] == ["510300", "000001", "000001"]
    etf = result.quotes[0]
    assert etf.name == "配置ETF名称"
    assert etf.price == Decimal("4.751")
    assert etf.previous_close == Decimal("4.709")
    assert etf.volume == 9_435_356
    assert etf.turnover == Decimal("447469")
    assert etf.timestamp == datetime(
        2026,
        8,
        7,
        16,
        14,
        52,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    assert all(quote.source == "tencent" for quote in result.quotes)


def test_parser_isolates_missing_and_invalid_instrument() -> None:
    lines = _fixture().splitlines()
    lines[0] = _replace_field(lines[0], PRICE_INDEX, "invalid")
    response = "\n".join(line for line in lines if "sh000001" not in line)

    result = TencentQuoteParser().parse(response, _instruments())

    assert [quote.instrument.type for quote in result.quotes] == [InstrumentType.STOCK]
    assert [failure.instrument.type for failure in result.failures] == [
        InstrumentType.ETF,
        InstrumentType.INDEX,
    ]
    assert all(failure.retryable for failure in result.failures)


def test_parser_rejects_response_with_unrequested_symbol() -> None:
    with pytest.raises(TencentResponseError, match="未请求"):
        TencentQuoteParser().parse(_fixture(), _instruments()[:1])


def test_parser_rejects_corrupted_response_envelope() -> None:
    with pytest.raises(TencentResponseError, match="结构非法"):
        TencentQuoteParser().parse("not a tencent response", _instruments())


def test_parser_marks_duplicate_record_as_single_failure() -> None:
    line = _fixture().splitlines()[0]
    response = f"{line}\n{line}\n"

    result = TencentQuoteParser().parse(response, _instruments()[:1])

    assert result.quotes == ()
    assert len(result.failures) == 1
    assert "重复记录" in result.failures[0].message


def test_parser_rejects_non_positive_current_price() -> None:
    response = _replace_field(_fixture().splitlines()[0], PRICE_INDEX, "0")

    result = TencentQuoteParser().parse(response, _instruments()[:1])

    assert result.quotes == ()
    assert "当前价和昨收必须大于 0" in result.failures[0].message


def test_parser_rejects_symbol_with_mismatched_internal_code() -> None:
    line = _replace_field(_fixture().splitlines()[0], CODE_INDEX, "510301")

    result = TencentQuoteParser().parse(line, _instruments()[:1])

    assert result.quotes == ()
    assert "证券代码与请求不一致" in result.failures[0].message


def test_parser_rejects_invalid_price_decimal() -> None:
    line = _replace_field(_fixture().splitlines()[0], PRICE_INDEX, "invalid")

    result = TencentQuoteParser().parse(line, _instruments()[:1])

    assert result.quotes == ()
    assert "price 不是有效 Decimal" in result.failures[0].message


def test_parser_rejects_invalid_previous_close_decimal() -> None:
    line = _replace_field(_fixture().splitlines()[0], PREVIOUS_CLOSE_INDEX, "invalid")

    result = TencentQuoteParser().parse(line, _instruments()[:1])

    assert result.quotes == ()
    assert "previous_close 不是有效 Decimal" in result.failures[0].message


@pytest.mark.parametrize("value", ["NaN", "Infinity"])
def test_parser_rejects_non_finite_decimal(value: str) -> None:
    line = _replace_field(_fixture().splitlines()[0], PRICE_INDEX, value)

    result = TencentQuoteParser().parse(line, _instruments()[:1])

    assert result.quotes == ()
    assert "price 必须是非负有限数值" in result.failures[0].message


def test_parser_rejects_invalid_timestamp() -> None:
    line = _replace_field(_fixture().splitlines()[0], TIMESTAMP_INDEX, "20260808999999")

    result = TencentQuoteParser().parse(line, _instruments()[:1])

    assert result.quotes == ()
    assert "quote_time 格式非法" in result.failures[0].message


def test_parser_rejects_insufficient_field_count() -> None:
    line = _truncate_fields(_fixture().splitlines()[0], 10)

    result = TencentQuoteParser().parse(line, _instruments()[:1])

    assert result.quotes == ()
    assert "字段数量不足" in result.failures[0].message


def test_parser_isolates_one_invalid_quote_in_batch() -> None:
    lines = _fixture().splitlines()
    lines[0] = _replace_field(lines[0], PRICE_INDEX, "invalid")

    result = TencentQuoteParser().parse("\n".join(lines), _instruments())

    assert [quote.instrument.type for quote in result.quotes] == [
        InstrumentType.INDEX,
        InstrumentType.STOCK,
    ]
    assert len(result.failures) == 1
    assert result.failures[0].instrument.type is InstrumentType.ETF
