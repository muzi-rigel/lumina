"""行情数据源的公共领域接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


class MarketSourceError(RuntimeError):
    """行情源访问或数据解析失败。"""


@dataclass(frozen=True)
class MarketQuote:
    """数据源标准化后的最小行情快照。"""

    symbol: str
    name: str
    price: Decimal
    timestamp: datetime
    source: str


class MarketSource(ABC):
    """所有行情供应方必须实现的统一接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """返回稳定的数据源标识。"""

    @abstractmethod
    def fetch_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        """批量获取并标准化行情。"""
