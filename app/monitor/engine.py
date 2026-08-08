"""行情历史、规则计算和告警状态的统一协调器。"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from app.market.model import MarketQuote
from app.monitor.formatting import format_percent
from app.monitor.history import HistoryUpdateStatus, QuoteHistory
from app.monitor.model import AlertEvent, MatchStatus, RuleEvaluation
from app.monitor.rules import MonitorRule
from app.monitor.state import AlertStateStore

logger = logging.getLogger(__name__)


class MonitorEngine:
    """评估单条统一行情，并返回本次新产生的告警。"""

    def __init__(
        self,
        rules: Iterable[MonitorRule],
        history: QuoteHistory,
        state_store: AlertStateStore,
    ) -> None:
        self._rules = tuple(rules)
        self._history = history
        self._state_store = state_store

    @staticmethod
    def _build_alert(
        quote: MarketQuote,
        rule: MonitorRule,
        evaluation: RuleEvaluation,
    ) -> AlertEvent | None:
        actual = evaluation.actual_change_percent
        reference_price = evaluation.reference_price
        if actual is None or reference_price is None:
            logger.error(
                "规则匹配结果缺少指标 code=%s rule_id=%s",
                quote.symbol,
                rule.definition.id,
            )
            return None
        effective_threshold = rule.definition.effective_threshold
        message = (
            f"{rule.definition.name}：实际涨跌幅 {format_percent(actual)}% "
            f"达到触发线 {format_percent(effective_threshold)}%"
        )
        return AlertEvent(
            code=quote.symbol,
            name=quote.name,
            instrument_type=quote.instrument.type,
            rule_id=rule.definition.id,
            rule_name=rule.definition.name,
            rule_type=rule.definition.type,
            direction=rule.definition.direction,
            severity=rule.definition.severity,
            triggered_at=quote.timestamp,
            current_price=quote.price,
            actual_change_percent=actual,
            threshold=rule.definition.threshold,
            window_seconds=rule.definition.window_seconds,
            reference_price=reference_price,
            reference_time=evaluation.reference_time,
            message=message,
        )

    def _evaluate_rule(self, quote: MarketQuote, rule: MonitorRule) -> AlertEvent | None:
        evaluation = rule.evaluate(quote, self._history)
        should_trigger = self._state_store.should_trigger(
            code=quote.symbol,
            rule_id=rule.definition.id,
            status=evaluation.status,
            observed_at=quote.timestamp,
            cooldown_seconds=rule.definition.cooldown_seconds,
        )
        if not should_trigger or evaluation.status is not MatchStatus.MATCHED:
            return None
        return self._build_alert(quote, rule, evaluation)

    def evaluate(self, quote: MarketQuote) -> list[AlertEvent]:
        """更新历史后逐规则评估，单条规则异常不会影响其他规则。"""

        update = self._history.add(quote)
        if update.status is HistoryUpdateStatus.OUT_OF_ORDER:
            logger.warning(
                "拒绝乱序行情 code=%s quote_time=%s",
                quote.symbol,
                quote.timestamp.isoformat(timespec="seconds"),
            )
            return []
        if update.date_changed:
            self._state_store.reset_code(quote.symbol)
            logger.info("自然日期变化，已重置监控状态 code=%s", quote.symbol)

        alerts: list[AlertEvent] = []
        for rule in self._rules:
            if not rule.applies_to(quote):
                continue
            try:
                alert = self._evaluate_rule(quote, rule)
            except Exception as exc:
                logger.error(
                    "规则执行异常 rule_id=%s code=%s error_type=%s reason=%s",
                    rule.definition.id,
                    quote.symbol,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                continue
            if alert is not None:
                alerts.append(alert)
        return alerts
