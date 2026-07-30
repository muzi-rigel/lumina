"""Lumina 标准日志初始化。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 10


def configure_logging(level: str, log_file: Path) -> None:
    """同时配置控制台日志和带轮转的文件日志。"""

    formatter = logging.Formatter(DEFAULT_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, level),
        handlers=[console_handler, file_handler],
        force=True,
    )
