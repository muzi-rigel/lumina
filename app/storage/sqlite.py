"""SQLite 连接与事务管理。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class StorageError(RuntimeError):
    """SQLite 初始化或事务执行失败。"""


class SQLiteStorage:
    """提供可靠的 SQLite 连接参数和事务边界。"""

    def __init__(self, database_path: Path, busy_timeout_seconds: float) -> None:
        self._database_path = database_path
        self._busy_timeout_seconds = busy_timeout_seconds

    def connect(self) -> sqlite3.Connection:
        """创建启用 WAL、外键和忙等待的独立连接。"""

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
            raise StorageError(f"无法连接 SQLite：{self._database_path}") from exc

    def initialize(self) -> None:
        """验证数据库可写；业务表将在对应功能开发时创建。"""

        connection = self.connect()
        connection.close()

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
        finally:
            connection.close()
