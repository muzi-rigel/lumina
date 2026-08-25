"""Lumina 数据库维护命令，仅供独立 oneshot 服务调用。"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import AppConfig, ConfigError, load_config
from app.storage.backup import BackupError, create_backup, rotate_backups
from app.storage.database import SQLiteDatabase, StorageError
from app.storage.retention import prune_quote_snapshots

logger = logging.getLogger(__name__)


def run_maintenance(config: AppConfig, *, now: datetime | None = None) -> None:
    """严格按备份、校验、清理、轮转顺序执行每日维护。"""

    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    database = SQLiteDatabase(config.storage.path, config.storage.busy_timeout_seconds)
    database.initialize()

    # 备份创建函数已包含 quick_check；失败会直接中断，禁止进入清理阶段。
    backup_path = create_backup(database, config.storage.backup.directory, now=current_time)
    logger.info("SQLite 在线备份成功 path=%s", backup_path)

    result = prune_quote_snapshots(
        database,
        quote_days=config.storage.retention.quote_days,
        batch_size=config.storage.retention.delete_batch_size,
        now=current_time,
    )
    logger.info(
        "SQLite 保留清理完成 deleted_quotes=%d cutoff=%s",
        result.deleted_quotes,
        result.cutoff.isoformat(),
    )

    removed = rotate_backups(
        config.storage.backup.directory,
        config.storage.backup.keep_count,
    )
    logger.info("SQLite 备份轮转完成 removed=%d", len(removed))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lumina SQLite 每日维护")
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--stocks", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """维护命令入口，错误时返回非零状态供 systemd 告警。"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _build_parser().parse_args(argv)
    try:
        config = load_config(args.settings, args.stocks, args.rules)
        run_maintenance(config)
    except (ConfigError, StorageError, BackupError, OSError) as exc:
        logger.error("Lumina 数据库维护失败：%s", exc)
        return 1
    except Exception:
        logger.exception("Lumina 数据库维护发生未预期异常")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
