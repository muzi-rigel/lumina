from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.model import InstrumentType
from app.monitor.model import (
    AlertEvent,
    AlertSeverity,
    RuleDirection,
    RuleType,
)
from app.storage.database import SQLiteDatabase
from app.storage.repository import SQLiteMarketRepository
from tests.factories import make_quote

SHANGHAI = ZoneInfo("Asia/Shanghai")
QUOTE_TIME = datetime(2026, 8, 8, 9, 30, tzinfo=SHANGHAI)
CREATED_AT = datetime(2026, 8, 8, 1, 31, tzinfo=UTC)


def _database(tmp_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "lumina.db", busy_timeout_seconds=1)
    database.initialize()
    return database


def _alert(rule_id: str = "day-fall") -> AlertEvent:
    return AlertEvent(
        code="510300",
        name="沪深300ETF",
        instrument_type=InstrumentType.ETF,
        rule_id=rule_id,
        rule_name="日内下跌",
        rule_type=RuleType.DAY_CHANGE_PERCENT,
        direction=RuleDirection.FALL,
        severity=AlertSeverity.CRITICAL,
        triggered_at=QUOTE_TIME,
        current_price=Decimal("3.95"),
        actual_change_percent=Decimal("-1.25"),
        threshold=Decimal("1.0"),
        window_seconds=None,
        reference_price=Decimal("4"),
        reference_time=None,
        message="测试告警",
    )


def test_initialize_creates_expected_tables_columns_and_indexes(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.initialize()

    with database.session() as connection:
        quote_columns = [row[1] for row in connection.execute("PRAGMA table_info(quote_snapshot)")]
        alert_columns = [row[1] for row in connection.execute("PRAGMA table_info(alert_event)")]
        indexes = {
            row[1]
            for row in connection.execute(
                "SELECT type, name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert quote_columns == [
        "id",
        "code",
        "name",
        "instrument_type",
        "price",
        "change_pct",
        "volume",
        "quote_time",
        "created_at",
    ]
    assert alert_columns == [
        "id",
        "code",
        "name",
        "rule_id",
        "severity",
        "actual_change",
        "threshold",
        "trigger_time",
    ]
    assert "uq_quote_snapshot_code_time" in indexes
    assert "uq_alert_event_identity" in indexes
    assert "idx_alert_event_rule_time" in indexes


def test_repository_saves_quote_as_text_and_null_change(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = SQLiteMarketRepository(database, clock=lambda: CREATED_AT)
    repository.save_quote_snapshot(
        make_quote(QUOTE_TIME, price="10.123456789", previous_close="10")
    )
    repository.save_quote_snapshot(
        make_quote(
            QUOTE_TIME,
            code="000001",
            instrument_type=InstrumentType.INDEX,
            price="0",
            previous_close="0",
        )
    )

    with database.session() as connection:
        rows = connection.execute(
            """
            SELECT code, instrument_type, price, change_pct, quote_time, created_at
            FROM quote_snapshot ORDER BY code
            """
        ).fetchall()

    assert rows == [
        (
            "000001",
            "INDEX",
            "0",
            None,
            "2026-08-08T01:30:00.000000+00:00",
            "2026-08-08T01:31:00.000000+00:00",
        ),
        (
            "510300",
            "ETF",
            "10.123456789",
            "1.2345678900",
            "2026-08-08T01:30:00.000000+00:00",
            "2026-08-08T01:31:00.000000+00:00",
        ),
    ]


def test_quote_upsert_uses_last_write_wins(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = SQLiteMarketRepository(database, clock=lambda: CREATED_AT)
    repository.save_quote_snapshot(make_quote(QUOTE_TIME, price="10"))
    repository.save_quote_snapshot(make_quote(QUOTE_TIME, name="新名称", price="11"))

    with database.session() as connection:
        rows = connection.execute("SELECT name, price, change_pct FROM quote_snapshot").fetchall()

    assert rows == [("新名称", "11", "10.0")]


def test_alert_write_is_idempotent_and_omits_message(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = SQLiteMarketRepository(database)
    repository.save_alert_event(_alert())
    repository.save_alert_event(_alert())

    with database.session() as connection:
        rows = connection.execute(
            """
            SELECT code, name, rule_id, severity, actual_change, threshold, trigger_time
            FROM alert_event
            """
        ).fetchall()

    assert rows == [
        (
            "510300",
            "沪深300ETF",
            "day-fall",
            "CRITICAL",
            "-1.25",
            "1.0",
            "2026-08-08T01:30:00.000000+00:00",
        )
    ]
