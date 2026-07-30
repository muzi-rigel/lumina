"""Lumina 标准日志初始化。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.config import LoggingConfig

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(config: LoggingConfig) -> None:
    """配置控制台日志，并按需启用带轮转的文件日志。"""

    formatter = logging.Formatter(DEFAULT_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [console_handler]

    if config.file_path is not None:
        config.file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.file_path,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, config.level),
        handlers=handlers,
        force=True,
    )
