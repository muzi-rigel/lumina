"""行情数据源协议及批量查询结果。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.market.model import MarketInstrument, MarketQuote


class MarketSourceError(RuntimeError):
    """整个行情源不可用或响应无法解析。"""


@dataclass(frozen=True, slots=True)
class QuoteFailure:
    """单个标的获取失败，不应中断同批其他标的。"""

    instrument: MarketInstrument
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("失败原因不能为空")


@dataclass(frozen=True, slots=True)
class QuoteBatch:
    """一次批量行情查询的标准化结果。"""

    source: str
    requested_at: datetime
    quotes: tuple[MarketQuote, ...] = ()
    failures: tuple[QuoteFailure, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("行情源名称不能为空")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("请求时间必须包含时区")
        if any(quote.source != self.source for quote in self.quotes):
            raise ValueError("批次与行情快照的 source 必须一致")

    @property
    def is_complete(self) -> bool:
        return not self.failures


class MarketSource(ABC):
    """所有行情供应方必须实现的统一批量接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """返回稳定的数据源标识。"""

    @abstractmethod
    def fetch_quotes(self, instruments: Sequence[MarketInstrument]) -> QuoteBatch:
        """批量获取行情；单标的异常通过 failures 返回。"""
