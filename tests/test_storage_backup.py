from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.storage.backup import (
    BackupError,
    create_backup,
    restore_backup,
    rotate_backups,
    verify_backup,
)
from app.storage.database import SQLiteDatabase


def _database(path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(path, busy_timeout_seconds=1)
    database.initialize()
    return database


def test_online_backup_and_restore_include_committed_wal_data(tmp_path: Path) -> None:
    database = _database(tmp_path / "live.db")
    writer = database.connect()
    try:
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute(
            """
            INSERT INTO quote_snapshot
                (code, name, instrument_type, price, change_pct, volume,
                 quote_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "510300",
                "沪深300ETF",
                "ETF",
                "4.10",
                "1.00",
                100,
                "2026-08-17T01:00:00+00:00",
                "2026-08-17T01:00:01+00:00",
            ),
        )
        writer.commit()
        backup = create_backup(
            database,
            tmp_path / "backups",
            now=datetime(2026, 8, 17, 2, tzinfo=UTC),
        )
    finally:
        writer.close()
    verify_backup(backup)
    restored = restore_backup(backup, tmp_path / "restored.db")

    restored_database = SQLiteDatabase(restored, busy_timeout_seconds=1)
    with restored_database.session() as connection:
        row = connection.execute("SELECT code, price FROM quote_snapshot").fetchone()
    assert row == ("510300", "4.10")
    assert backup.stat().st_mode & 0o777 == 0o600
    assert restored.stat().st_mode & 0o777 == 0o600


def test_restore_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    database = _database(tmp_path / "live.db")
    backup = create_backup(database, tmp_path / "backups")
    target = tmp_path / "existing.db"
    target.touch()

    with pytest.raises(BackupError, match="恢复目标已存在"):
        restore_backup(backup, target)


def test_rotate_backups_keeps_fourteen_and_ignores_other_files(tmp_path: Path) -> None:
    base = datetime(2026, 8, 1, tzinfo=UTC)
    paths = []
    for offset in range(16):
        path = tmp_path / (base + timedelta(days=offset)).strftime("lumina-%Y%m%dT%H%M%SZ.db")
        path.touch()
        paths.append(path)
    unrelated = tmp_path / "other.db"
    unrelated.touch()

    removed = rotate_backups(tmp_path, 14)

    assert set(removed) == set(paths[:2])
    assert unrelated.exists()
    assert len(list(tmp_path.glob("lumina-*.db"))) == 14
