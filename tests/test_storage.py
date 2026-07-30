from pathlib import Path

import pytest

from app.storage.sqlite import SQLiteStorage, StorageError


def test_sqlite_session_commits_data(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "lumina.db", busy_timeout_seconds=1)

    with storage.session() as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES (?)", ("ok",))

    with storage.session() as connection:
        row = connection.execute("SELECT value FROM sample").fetchone()

    assert row == ("ok",)


def test_sqlite_session_wraps_database_errors(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "lumina.db", busy_timeout_seconds=1)

    with pytest.raises(StorageError), storage.session() as connection:
        connection.execute("SELECT * FROM missing_table")
