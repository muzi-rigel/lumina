from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import (
    AppConfig,
    BackupSettings,
    RetentionSettings,
    StorageSettings,
    load_config,
)
from app.maintenance import run_maintenance
from app.storage.backup import BackupError
from app.storage.database import SQLiteDatabase


def _config(tmp_path: Path) -> AppConfig:
    base = load_config(
        Path("config/settings.yaml"),
        Path("config/stocks.yaml"),
        Path("config/rules.yaml"),
    )
    return AppConfig(
        app=base.app,
        runtime=base.runtime,
        market=base.market,
        storage=StorageSettings(
            type="sqlite",
            path=tmp_path / "lumina.db",
            busy_timeout_seconds=1,
            retention=RetentionSettings(quote_days=30, delete_batch_size=1),
            backup=BackupSettings(directory=tmp_path / "backups", keep_count=14),
        ),
        notify=base.notify,
        stocks=base.stocks,
        rules=base.rules,
    )


def _insert_old_quote(database: SQLiteDatabase) -> None:
    database.initialize()
    with database.session() as connection:
        connection.execute(
            """
            INSERT INTO quote_snapshot
                (code, name, instrument_type, price, change_pct, volume,
                 quote_time, created_at)
            VALUES ('000001', '上证指数', 'INDEX', '10', '0', 0,
                    '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')
            """
        )


def test_maintenance_creates_backup_before_pruning(tmp_path: Path) -> None:
    config = _config(tmp_path)
    database = SQLiteDatabase(config.storage.path, busy_timeout_seconds=1)
    _insert_old_quote(database)

    run_maintenance(config, now=datetime(2026, 8, 17, tzinfo=UTC))

    backup_path = tmp_path / "backups/lumina-20260817T000000Z.db"
    backup_database = SQLiteDatabase(backup_path, busy_timeout_seconds=1)
    with backup_database.session() as connection:
        backup_count = connection.execute("SELECT COUNT(*) FROM quote_snapshot").fetchone()
    with database.session() as connection:
        live_count = connection.execute("SELECT COUNT(*) FROM quote_snapshot").fetchone()
    assert backup_count == (1,)
    assert live_count == (0,)


def test_backup_failure_prevents_retention(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(tmp_path)
    database = SQLiteDatabase(config.storage.path, busy_timeout_seconds=1)
    _insert_old_quote(database)

    def fail_backup(*args: object, **kwargs: object) -> Path:
        raise BackupError("forced failure")

    monkeypatch.setattr("app.maintenance.create_backup", fail_backup)
    with pytest.raises(BackupError, match="forced failure"):
        run_maintenance(config, now=datetime(2026, 8, 17, tzinfo=UTC))

    with database.session() as connection:
        count = connection.execute("SELECT COUNT(*) FROM quote_snapshot").fetchone()
    assert count == (1,)
