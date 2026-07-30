"""监控规则执行引擎。"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from app.market.source import MarketQuote
from app.monitor.rules import MonitorRule, RuleResult

logger = logging.getLogger(__name__)


class MonitorEngine:
    """串行执行规则，并隔离单条行情或规则异常。"""

    def __init__(self, rules: Iterable[MonitorRule] = ()) -> None:
        self._rules = list(rules)

    def add_rule(self, rule: MonitorRule) -> None:
        if any(item.name == rule.name for item in self._rules):
            raise ValueError(f"规则名称重复：{rule.name}")
        self._rules.append(rule)

    def evaluate(self, quotes: Iterable[MarketQuote]) -> list[RuleResult]:
        results: list[RuleResult] = []
        for quote in quotes:
            for rule in self._rules:
                try:
                    result = rule.evaluate(quote)
                except Exception:
                    logger.exception(
                        "监控规则执行失败，symbol=%s rule=%s",
                        quote.symbol,
                        rule.name,
                    )
                    continue
                if result.triggered:
                    results.append(result)
        return results
