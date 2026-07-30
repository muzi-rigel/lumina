"""与具体行情供应方无关的标准化数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class InstrumentType(StrEnum):
    """Lumina 当前支持的监控标的类型。"""

    STOCK = "STOCK"
    ETF = "ETF"
    INDEX = "INDEX"


@dataclass(frozen=True, slots=True)
class MarketInstrument:
    """行情查询和监控使用的标的身份信息。"""

    code: str
    name: str
    type: InstrumentType

    def __post_init__(self) -> None:
        if len(self.code) != 6 or not self.code.isdigit():
            raise ValueError("证券代码必须是 6 位数字")
        if not self.name.strip():
            raise ValueError("证券名称不能为空")
        if not isinstance(self.type, InstrumentType):
            raise TypeError("标的类型必须是 InstrumentType")


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """某一时刻的标准化行情快照。"""

    instrument: MarketInstrument
    timestamp: datetime
    source: str
    price: Decimal
    previous_close: Decimal
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: int
    turnover: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("行情时间必须包含时区")
        if not self.source.strip():
            raise ValueError("行情源名称不能为空")

        prices = {
            "price": self.price,
            "previous_close": self.previous_close,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "turnover": self.turnover,
        }
        for field, value in prices.items():
            if not isinstance(value, Decimal):
                raise TypeError(f"{field} 必须使用 Decimal")
            if not value.is_finite() or value < 0:
                raise ValueError(f"{field} 必须是非负有限数值")

        if isinstance(self.volume, bool) or not isinstance(self.volume, int):
            raise TypeError("volume 必须是整数")
        if self.volume < 0:
            raise ValueError("volume 不能小于 0")
        if self.high_price < self.low_price:
            raise ValueError("high_price 不能小于 low_price")

    @property
    def symbol(self) -> str:
        """兼容监控层使用的证券代码名称。"""

        return self.instrument.code

    @property
    def name(self) -> str:
        return self.instrument.name

    @property
    def change(self) -> Decimal:
        """相对昨收的涨跌额。"""

        return self.price - self.previous_close

    @property
    def change_percent(self) -> Decimal | None:
        """相对昨收的涨跌百分比；昨收为零时不可计算。"""

        if self.previous_close == 0:
            return None
        return self.change / self.previous_close * Decimal("100")
