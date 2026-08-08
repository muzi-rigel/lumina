"""行情快照与告警事件的持久化 Repository。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.market.model import MarketQuote
from app.monitor.model import AlertEvent
from app.storage.database import SQLiteDatabase
from app.storage.models import AlertEventRecord, QuoteSnapshotRecord


class MarketRepository(Protocol):
    """Collector 使用的最小持久化接口。"""

    def save_quote_snapshot(self, quote: MarketQuote) -> None:
        """保存或替换同代码、同时间的行情。"""

    def save_alert_event(self, alert: AlertEvent) -> None:
        """幂等保存一次规则告警。"""


class SQLiteMarketRepository:
    """基于短事务实现行情和告警的 SQLite Repository。"""

    def __init__(
        self,
        database: SQLiteDatabase,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._database = database
        self._clock = clock or (lambda: datetime.now(UTC))

    def save_quote_snapshot(self, quote: MarketQuote) -> None:
        record = QuoteSnapshotRecord.from_quote(quote, self._clock())
        values = (
            record.code,
            record.name,
            record.instrument_type,
            str(record.price),
            None if record.change_pct is None else str(record.change_pct),
            record.volume,
            record.quote_time,
            record.created_at,
        )
        with self._database.session() as connection:
            connection.execute(
                """
                INSERT INTO quote_snapshot (
                    code, name, instrument_type, price, change_pct,
                    volume, quote_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, quote_time) DO UPDATE SET
                    name = excluded.name,
                    instrument_type = excluded.instrument_type,
                    price = excluded.price,
                    change_pct = excluded.change_pct,
                    volume = excluded.volume,
                    created_at = excluded.created_at
                """,
                values,
            )

    def save_alert_event(self, alert: AlertEvent) -> None:
        record = AlertEventRecord.from_alert(alert)
        with self._database.session() as connection:
            connection.execute(
                """
                INSERT INTO alert_event (
                    code, name, rule_id, severity,
                    actual_change, threshold, trigger_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, rule_id, trigger_time) DO NOTHING
                """,
                (
                    record.code,
                    record.name,
                    record.rule_id,
                    record.severity,
                    str(record.actual_change),
                    str(record.threshold),
                    record.trigger_time,
                ),
            )
