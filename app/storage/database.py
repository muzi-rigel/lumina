"""SQLite 数据库连接、事务和表结构初始化。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS quote_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        instrument_type TEXT NOT NULL,
        price TEXT NOT NULL,
        change_pct TEXT,
        volume INTEGER NOT NULL CHECK (volume >= 0),
        quote_time TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_quote_snapshot_code_time
    ON quote_snapshot (code, quote_time)
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        rule_id TEXT NOT NULL,
        severity TEXT NOT NULL,
        actual_change TEXT NOT NULL,
        threshold TEXT NOT NULL,
        trigger_time TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_event_identity
    ON alert_event (code, rule_id, trigger_time)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_alert_event_rule_time
    ON alert_event (rule_id, trigger_time)
    """,
)


class StorageError(RuntimeError):
    """SQLite 初始化、连接或事务执行失败。"""


class SQLiteDatabase:
    """提供适合长期服务使用的 SQLite 连接和短事务边界。"""

    def __init__(self, database_path: Path, busy_timeout_seconds: float) -> None:
        self._database_path = database_path
        self._busy_timeout_seconds = busy_timeout_seconds

    def connect(self) -> sqlite3.Connection:
        """创建启用 WAL、外键和忙等待的独立连接。"""

        connection: sqlite3.Connection | None = None
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._database_path,
                timeout=self._busy_timeout_seconds,
            )
            timeout_ms = int(self._busy_timeout_seconds * 1000)
            connection.execute(f"PRAGMA busy_timeout = {timeout_ms}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            return connection
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise StorageError(f"无法连接 SQLite：{self._database_path}") from exc

    def initialize(self) -> None:
        """幂等创建当前阶段所需的业务表和索引。"""

        with self.session() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """提供自动提交、异常回滚和连接关闭的事务上下文。"""

        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StorageError("SQLite 事务执行失败") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
