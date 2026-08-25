from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import app.core.logger as logger_module
from app.core.logger import DEFAULT_BACKUP_COUNT, DEFAULT_MAX_BYTES, configure_logging


def test_logging_uses_bounded_rotating_file_handler(tmp_path: Path) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    try:
        configure_logging("INFO", tmp_path / "lumina.log")
        rotating_handlers = [
            handler for handler in root.handlers if isinstance(handler, RotatingFileHandler)
        ]
        assert len(rotating_handlers) == 1
        assert rotating_handlers[0].maxBytes == DEFAULT_MAX_BYTES
        assert rotating_handlers[0].backupCount == DEFAULT_BACKUP_COUNT
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = original_handlers
        root.setLevel(original_level)


def test_file_logging_really_rolls_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    monkeypatch.setattr(logger_module, "DEFAULT_MAX_BYTES", 80)
    monkeypatch.setattr(logger_module, "DEFAULT_BACKUP_COUNT", 2)
    try:
        log_file = tmp_path / "lumina.log"
        configure_logging("INFO", log_file)
        for index in range(20):
            logging.getLogger("rotation-test").info("event=%d payload=%s", index, "x" * 30)
        assert log_file.exists()
        assert (tmp_path / "lumina.log.1").exists()
        assert len(list(tmp_path.glob("lumina.log.*"))) <= 2
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = original_handlers
        root.setLevel(original_level)
