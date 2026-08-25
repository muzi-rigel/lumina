"""systemd 启动前的轻量本地环境检查。"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from app.core.config import AppConfig, ConfigError, load_config
from app.storage.database import SQLiteDatabase, StorageError


class PreflightError(RuntimeError):
    """启动前本地检查失败。"""


def _check_writable_directory(path: Path, label: str) -> None:
    """通过短生命周期临时文件验证目录确实可写。"""

    try:
        path.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".lumina-check-", dir=path)
        os.close(descriptor)
        Path(temporary_name).unlink()
    except OSError as exc:
        raise PreflightError(f"{label}不可写：{path}") from exc


def run_preflight(config: AppConfig, log_directory: Path) -> None:
    """只检查目录权限和 SQLite 连接，不访问任何外部网络。"""

    _check_writable_directory(log_directory, "日志目录")
    _check_writable_directory(config.storage.path.parent, "数据目录")
    database = SQLiteDatabase(config.storage.path, config.storage.busy_timeout_seconds)
    try:
        with database.session() as connection:
            result = connection.execute("SELECT 1").fetchone()
    except (StorageError, sqlite3.Error) as exc:
        raise PreflightError(f"SQLite 无法连接：{config.storage.path}") from exc
    if result != (1,):
        raise PreflightError(f"SQLite 连接检查返回异常：{config.storage.path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lumina 启动前本地检查")
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--stocks", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        config = load_config(args.settings, args.stocks, args.rules)
        run_preflight(config, args.log_dir)
    except (ConfigError, PreflightError) as exc:
        print(f"Lumina 启动前检查失败：{exc}", file=sys.stderr)
        return 2
    print("Lumina 启动前检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
