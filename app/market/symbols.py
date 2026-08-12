"""Lumina 标的到供应方证券标识的领域映射。"""

from __future__ import annotations

from app.market.model import InstrumentType, MarketInstrument


class SymbolMappingError(ValueError):
    """标的代码和类型无法确定所属交易所。"""


def to_tencent_symbol(instrument: MarketInstrument) -> str:
    """结合标的类型映射沪深市场，避免仅凭代码产生歧义。"""

    code = instrument.code
    if instrument.type is InstrumentType.INDEX:
        if code.startswith("000"):
            return f"sh{code}"
        if code.startswith("399"):
            return f"sz{code}"
    elif instrument.type is InstrumentType.ETF:
        if code.startswith("5"):
            return f"sh{code}"
        if code.startswith("1"):
            return f"sz{code}"
    elif instrument.type is InstrumentType.STOCK:
        if code.startswith("6"):
            return f"sh{code}"
        if code.startswith(("0", "3")):
            return f"sz{code}"
    raise SymbolMappingError(f"无法映射腾讯证券标识：code={code} type={instrument.type.value}")
