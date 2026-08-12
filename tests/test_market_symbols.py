import pytest

from app.market.model import InstrumentType, MarketInstrument
from app.market.symbols import SymbolMappingError, to_tencent_symbol


def test_same_code_uses_instrument_type_to_select_different_exchange() -> None:
    index = MarketInstrument("000001", "上证指数", InstrumentType.INDEX)
    stock = MarketInstrument("000001", "平安银行", InstrumentType.STOCK)

    assert to_tencent_symbol(index) == "sh000001"
    assert to_tencent_symbol(stock) == "sz000001"


@pytest.mark.parametrize(
    ("code", "instrument_type", "expected"),
    [
        ("000001", InstrumentType.INDEX, "sh000001"),
        ("399001", InstrumentType.INDEX, "sz399001"),
        ("510300", InstrumentType.ETF, "sh510300"),
        ("159915", InstrumentType.ETF, "sz159915"),
        ("600519", InstrumentType.STOCK, "sh600519"),
        ("688981", InstrumentType.STOCK, "sh688981"),
        ("000001", InstrumentType.STOCK, "sz000001"),
        ("300750", InstrumentType.STOCK, "sz300750"),
    ],
)
def test_tencent_symbol_mapping(
    code: str,
    instrument_type: InstrumentType,
    expected: str,
) -> None:
    instrument = MarketInstrument(code, "测试标的", instrument_type)

    assert to_tencent_symbol(instrument) == expected


@pytest.mark.parametrize(
    ("code", "instrument_type"),
    [
        ("430047", InstrumentType.STOCK),
        ("200001", InstrumentType.STOCK),
        ("510300", InstrumentType.STOCK),
        ("000001", InstrumentType.ETF),
        ("888888", InstrumentType.INDEX),
    ],
)
def test_unknown_exchange_mapping_is_rejected(
    code: str,
    instrument_type: InstrumentType,
) -> None:
    with pytest.raises(SymbolMappingError, match="无法映射"):
        to_tencent_symbol(MarketInstrument(code, "未知标的", instrument_type))
