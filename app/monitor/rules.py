"""监控规则的公共接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.market.source import MarketQuote


@dataclass(frozen=True)
class RuleResult:
    """单条规则对一个行情快照的判断结果。"""

    rule_name: str
    symbol: str
    triggered: bool
    message: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class MonitorRule(ABC):
    """监控规则必须实现的稳定边界。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """返回规则唯一名称。"""

    @abstractmethod
    def evaluate(self, quote: MarketQuote) -> RuleResult:
        """判断单个行情快照是否触发异动。"""
