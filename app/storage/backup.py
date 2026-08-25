"""SQLite 在线备份、校验、恢复和备份轮转。"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.storage.database import SQLiteDatabase


class BackupError(RuntimeError):
    """备份、校验或恢复失败。"""


def verify_backup(path: Path) -> None:
    """对独立备份执行 SQLite 快速一致性检查。"""

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result != ("ok",):
            raise BackupError(f"SQLite 备份一致性检查失败：{path}")
    except sqlite3.Error as exc:
        raise BackupError(f"无法校验 SQLite 备份：{path}") from exc
    finally:
        if connection is not None:
            connection.close()


def create_backup(
    database: SQLiteDatabase,
    backup_directory: Path,
    *,
    now: datetime | None = None,
) -> Path:
    """使用 SQLite backup API 创建经校验的原子备份。"""

    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    destination = backup_directory / timestamp.strftime("lumina-%Y%m%dT%H%M%SZ.db")
    try:
        backup_directory.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise BackupError(f"备份文件已存在：{destination}")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".lumina-backup-",
            suffix=".tmp",
            dir=backup_directory,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        temporary_path.chmod(0o600)
    except OSError as exc:
        raise BackupError(f"无法准备备份目录：{backup_directory}") from exc

    source: sqlite3.Connection | None = None
    target: sqlite3.Connection | None = None
    try:
        source = database.connect()
        target = sqlite3.connect(temporary_path)
        source.backup(target)
        target.close()
        target = None
        verify_backup(temporary_path)
        os.replace(temporary_path, destination)
        return destination
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(f"创建 SQLite 在线备份失败：{destination}") from exc
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()
        temporary_path.unlink(missing_ok=True)


def restore_backup(backup_path: Path, restore_path: Path) -> Path:
    """恢复到全新路径并校验，用于恢复演练和灾难恢复。"""

    if restore_path.exists():
        raise BackupError(f"恢复目标已存在：{restore_path}")
    try:
        restore_path.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(f"{backup_path.resolve().as_uri()}?mode=ro", uri=True)
        target = sqlite3.connect(restore_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        restore_path.chmod(0o600)
        verify_backup(restore_path)
        return restore_path
    except BackupError:
        restore_path.unlink(missing_ok=True)
        raise
    except (OSError, sqlite3.Error) as exc:
        restore_path.unlink(missing_ok=True)
        raise BackupError(f"恢复 SQLite 备份失败：{backup_path}") from exc


def rotate_backups(backup_directory: Path, keep_count: int) -> tuple[Path, ...]:
    """仅删除超出保留数量的 Lumina 数据库备份。"""

    backups = sorted(backup_directory.glob("lumina-????????T??????Z.db"), reverse=True)
    removed: list[Path] = []
    for path in backups[keep_count:]:
        try:
            path.unlink()
        except OSError as exc:
            raise BackupError(f"无法删除过期备份：{path}") from exc
        removed.append(path)
    return tuple(removed)
