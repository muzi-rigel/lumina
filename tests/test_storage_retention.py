from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.storage.database import SQLiteDatabase
from app.storage.retention import prune_quote_snapshots


def _insert_quote(database: SQLiteDatabase, code: str, created_at: str) -> None:
    with database.session() as connection:
        connection.execute(
            """
            INSERT INTO quote_snapshot
                (code, name, instrument_type, price, change_pct, volume,
                 quote_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code, code, "STOCK", "10", "0", 0, created_at, created_at),
        )


def test_retention_deletes_old_quotes_in_batches_but_not_boundary(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "lumina.db", busy_timeout_seconds=1)
    database.initialize()
    _insert_quote(database, "000001", "2026-07-17T23:59:59+00:00")
    _insert_quote(database, "000002", "2026-07-18T00:00:00+00:00")
    _insert_quote(database, "000003", "2026-08-01T00:00:00+00:00")

    result = prune_quote_snapshots(
        database,
        quote_days=30,
        batch_size=1,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    with database.session() as connection:
        codes = connection.execute("SELECT code FROM quote_snapshot ORDER BY code").fetchall()
    assert result.deleted_quotes == 1
    assert codes == [("000002",), ("000003",)]


def test_retention_never_deletes_alert_events(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "lumina.db", busy_timeout_seconds=1)
    database.initialize()
    with database.session() as connection:
        connection.execute(
            """
            INSERT INTO alert_event
                (code, name, rule_id, severity, actual_change, threshold, trigger_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("000001", "上证指数", "day-rise", "WARNING", "3", "3", "2020-01-01"),
        )

    prune_quote_snapshots(
        database,
        quote_days=30,
        batch_size=10,
        now=datetime(2026, 8, 17, tzinfo=UTC),
    )

    with database.session() as connection:
        count = connection.execute("SELECT COUNT(*) FROM alert_event").fetchone()
    assert count == (1,)
