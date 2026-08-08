"""日内和窗口涨跌幅规则。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from app.market.model import MarketQuote
from app.monitor.history import QuoteHistory
from app.monitor.model import (
    MatchStatus,
    RuleDefinition,
    RuleDirection,
    RuleEvaluation,
    RuleType,
)


class MonitorRule(ABC):
    """所有异动规则必须实现的纯计算边界。"""

    def __init__(self, definition: RuleDefinition) -> None:
        self.definition = definition

    def applies_to(self, quote: MarketQuote) -> bool:
        return self.definition.targets.applies_to(quote.instrument)

    def _evaluation(
        self,
        actual: Decimal,
        reference_price: Decimal,
        reference_time: datetime | None,
    ) -> RuleEvaluation:
        if self.definition.direction is RuleDirection.RISE:
            matched = actual >= self.definition.threshold
        else:
            matched = actual <= -self.definition.threshold
        return RuleEvaluation(
            status=MatchStatus.MATCHED if matched else MatchStatus.NOT_MATCHED,
            actual_change_percent=actual,
            reference_price=reference_price,
            reference_time=reference_time,
        )

    @abstractmethod
    def evaluate(self, quote: MarketQuote, history: QuoteHistory) -> RuleEvaluation:
        """计算规则三态结果，不管理触发状态。"""


class DayChangePercentRule(MonitorRule):
    def evaluate(self, quote: MarketQuote, history: QuoteHistory) -> RuleEvaluation:
        del history
        actual = quote.change_percent
        if actual is None or quote.previous_close <= 0:
            return RuleEvaluation(MatchStatus.UNKNOWN, None, None, None)
        return self._evaluation(actual, quote.previous_close, None)


class WindowChangePercentRule(MonitorRule):
    def evaluate(self, quote: MarketQuote, history: QuoteHistory) -> RuleEvaluation:
        window_seconds = self.definition.window_seconds
        if window_seconds is None:
            return RuleEvaluation(MatchStatus.UNKNOWN, None, None, None)
        baseline = history.baseline(quote.symbol, quote.timestamp, window_seconds)
        if baseline is None:
            return RuleEvaluation(MatchStatus.UNKNOWN, None, None, None)
        if baseline.price <= 0:
            return RuleEvaluation(
                MatchStatus.UNKNOWN,
                None,
                baseline.price,
                baseline.timestamp,
            )
        actual = (quote.price - baseline.price) / baseline.price * Decimal("100")
        return self._evaluation(actual, baseline.price, baseline.timestamp)


def create_rule(definition: RuleDefinition) -> MonitorRule:
    """将配置定义转换为具体规则，不提供静默回退。"""

    if definition.type is RuleType.DAY_CHANGE_PERCENT:
        return DayChangePercentRule(definition)
    if definition.type is RuleType.WINDOW_CHANGE_PERCENT:
        return WindowChangePercentRule(definition)
    raise ValueError(f"不支持的规则类型：{definition.type}")
