"""批量行情采集和统一结果处理入口。"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.market.model import MarketInstrument, MarketQuote
from app.market.source import MarketSource, MarketSourceError, QuoteBatch, QuoteFailure
from app.monitor.engine import MonitorEngine
from app.monitor.formatting import format_percent
from app.monitor.model import AlertEvent, RuleDirection
from app.storage.repository import MarketRepository

logger = logging.getLogger(__name__)


class MarketCollector:
    """执行一次批量采集，并隔离源、标的和监控处理异常。"""

    def __init__(
        self,
        source: MarketSource,
        instruments: Sequence[MarketInstrument],
        monitor_engine: MonitorEngine,
        repository: MarketRepository,
    ) -> None:
        if not instruments:
            raise ValueError("行情采集标的不能为空")
        self._source = source
        self._instruments = tuple(instruments)
        self._monitor_engine = monitor_engine
        self._repository = repository

    @property
    def source_name(self) -> str:
        """返回行情源稳定名称，用于日志和启动信息。"""

        return self._source.name

    @staticmethod
    def _log_quote(quote: MarketQuote) -> None:
        change_percent = quote.change_percent
        percent_text = "N/A" if change_percent is None else f"{change_percent:.4f}%"
        logger.info(
            "行情成功 code=%s name=%s price=%s change=%s change_pct=%s quote_time=%s",
            quote.symbol,
            quote.name,
            quote.price,
            quote.change,
            percent_text,
            quote.timestamp.isoformat(timespec="seconds"),
        )

    def _process_quote(self, quote: MarketQuote) -> None:
        try:
            self._repository.save_quote_snapshot(quote)
        except Exception as exc:
            # 存储故障不能阻断实时检测，规则仍使用当前行情继续计算。
            logger.error(
                "行情保存失败 code=%s quote_time=%s error_type=%s reason=%s",
                quote.symbol,
                quote.timestamp.isoformat(timespec="seconds"),
                type(exc).__name__,
                exc,
                exc_info=True,
            )
        self._log_quote(quote)
        try:
            # 单条交给监控引擎，确保未知异常不会中断同批其他行情。
            alerts = self._monitor_engine.evaluate(quote)
        except Exception as exc:
            logger.error(
                "行情处理异常 code=%s error_type=%s reason=%s",
                quote.symbol,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return
        for alert in alerts:
            try:
                self._repository.save_alert_event(alert)
            except Exception as exc:
                logger.error(
                    "告警保存失败 code=%s rule_id=%s trigger_time=%s error_type=%s reason=%s",
                    alert.code,
                    alert.rule_id,
                    alert.triggered_at.isoformat(timespec="seconds"),
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
            self._log_alert(alert)

    @staticmethod
    def _log_alert(alert: AlertEvent) -> None:
        effective_threshold = (
            alert.threshold if alert.direction is RuleDirection.RISE else -alert.threshold
        )
        reference_time = (
            "N/A"
            if alert.reference_time is None
            else alert.reference_time.isoformat(timespec="seconds")
        )
        window_seconds = "N/A" if alert.window_seconds is None else str(alert.window_seconds)
        logger.warning(
            "alert rule_id=%s code=%s name=%s severity=%s direction=%s "
            "actual_change_pct=%s threshold=%s effective_threshold=%s "
            "reference_price=%s reference_time=%s window_seconds=%s triggered_at=%s",
            alert.rule_id,
            alert.code,
            alert.name,
            alert.severity,
            alert.direction,
            format_percent(alert.actual_change_percent),
            format_percent(alert.threshold),
            format_percent(effective_threshold),
            alert.reference_price,
            reference_time,
            window_seconds,
            alert.triggered_at.isoformat(timespec="seconds"),
        )

    @staticmethod
    def _log_failure(failure: QuoteFailure) -> None:
        logger.warning(
            "行情失败 code=%s reason=%s retryable=%s",
            failure.instrument.code,
            failure.message,
            failure.retryable,
        )

    def collect_once(self) -> QuoteBatch | None:
        """执行一个采集周期；系统级源故障只终止当前周期。"""

        try:
            batch = self._source.fetch_quotes(self._instruments)
        except MarketSourceError as exc:
            logger.error(
                "行情源故障 source=%s error_type=%s reason=%s",
                self._source.name,
                type(exc).__name__,
                exc,
            )
            return None

        for failure in batch.failures:
            self._log_failure(failure)
        for quote in batch.quotes:
            self._process_quote(quote)
        return batch
