"""按证券代码隔离的有界内存行情历史。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.market.model import MarketQuote


class HistoryUpdateStatus(StrEnum):
    ADDED = "ADDED"
    REPLACED = "REPLACED"
    OUT_OF_ORDER = "OUT_OF_ORDER"


@dataclass(frozen=True, slots=True)
class HistoryUpdateResult:
    status: HistoryUpdateStatus
    date_changed: bool = False


class QuoteHistory:
    """使用时间清理保证正确性，并以 maxlen 防御异常采样频率。"""

    def __init__(
        self,
        retention_seconds: int,
        max_points_per_symbol: int,
        timezone: ZoneInfo,
    ) -> None:
        if retention_seconds <= 0:
            raise ValueError("retention_seconds 必须大于 0")
        if max_points_per_symbol < 3:
            raise ValueError("max_points_per_symbol 不能小于 3")
        self._retention = timedelta(seconds=retention_seconds)
        self._max_points = max_points_per_symbol
        self._timezone = timezone
        self._quotes: dict[str, deque[MarketQuote]] = {}

    def _local_date(self, timestamp: datetime) -> date:
        return timestamp.astimezone(self._timezone).date()

    def _history_for(self, code: str) -> deque[MarketQuote]:
        history = self._quotes.get(code)
        if history is None:
            history = deque(maxlen=self._max_points)
            self._quotes[code] = history
        return history

    def add(self, quote: MarketQuote) -> HistoryUpdateResult:
        """追加行情；乱序拒绝，相同时间替换，新自然日期清空旧历史。"""

        history = self._history_for(quote.symbol)
        if history and quote.timestamp < history[-1].timestamp:
            return HistoryUpdateResult(HistoryUpdateStatus.OUT_OF_ORDER)

        date_changed = bool(
            history and self._local_date(quote.timestamp) != self._local_date(history[-1].timestamp)
        )
        if date_changed:
            history.clear()

        if history and quote.timestamp == history[-1].timestamp:
            history[-1] = quote
            return HistoryUpdateResult(HistoryUpdateStatus.REPLACED)

        history.append(quote)
        cutoff = quote.timestamp - self._retention
        while history and history[0].timestamp < cutoff:
            history.popleft()
        return HistoryUpdateResult(HistoryUpdateStatus.ADDED, date_changed=date_changed)

    def baseline(
        self,
        code: str,
        current_time: datetime,
        window_seconds: int,
    ) -> MarketQuote | None:
        """选择不晚于窗口边界的最近一条同自然日期行情。"""

        history = self._quotes.get(code)
        if not history:
            return None
        boundary = current_time - timedelta(seconds=window_seconds)
        current_date = self._local_date(current_time)
        for candidate in reversed(history):
            if self._local_date(candidate.timestamp) != current_date:
                continue
            if candidate.timestamp <= boundary:
                return candidate
        return None

    def size(self, code: str) -> int:
        """返回指定代码的当前历史条数，主要用于运行诊断和测试。"""

        return len(self._quotes.get(code, ()))
