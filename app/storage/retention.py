"""SQLite 行情快照的有界分批保留清理。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.storage.database import SQLiteDatabase


@dataclass(frozen=True)
class RetentionResult:
    """一次保留清理的结果。"""

    cutoff: datetime
    deleted_quotes: int


def prune_quote_snapshots(
    database: SQLiteDatabase,
    *,
    quote_days: int,
    batch_size: int,
    now: datetime | None = None,
) -> RetentionResult:
    """按写入时间分批删除过期行情，不清理告警事件。"""

    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    cutoff = current_time - timedelta(days=quote_days)
    cutoff_text = cutoff.isoformat()
    deleted_total = 0

    while True:
        with database.session() as connection:
            cursor = connection.execute(
                """
                DELETE FROM quote_snapshot
                WHERE id IN (
                    SELECT id FROM quote_snapshot
                    WHERE created_at < ?
                    ORDER BY created_at
                    LIMIT ?
                )
                """,
                (cutoff_text, batch_size),
            )
            deleted = cursor.rowcount
        deleted_total += deleted
        if deleted < batch_size:
            break

    with database.session() as connection:
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
    return RetentionResult(cutoff=cutoff, deleted_quotes=deleted_total)
