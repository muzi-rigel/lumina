"""Lumina 服务启动入口。"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from types import FrameType

from app.core.config import AppConfig, ConfigError, load_config
from app.core.logger import configure_logging
from app.core.scheduler import IntervalScheduler
from app.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


class LuminaService:
    """装配基础设施并管理服务生命周期。"""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._scheduler = IntervalScheduler(config.scheduler.interval_seconds)
        self._storage = SQLiteStorage(
            config.storage.database_path,
            config.storage.busy_timeout_seconds,
        )

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        del frame
        logger.info("收到停止信号，signal=%s", signal.Signals(signum).name)
        self._scheduler.stop()

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    @staticmethod
    def _heartbeat() -> None:
        logger.debug("Lumina 服务心跳正常")

    def run(self) -> None:
        """初始化依赖并运行，直到收到系统停止信号。"""

        self._install_signal_handlers()
        self._storage.initialize()
        self._scheduler.add_task("lumina-heartbeat", self._heartbeat)

        logger.info(
            "Lumina 服务启动，database=%s",
            self._config.storage.database_path,
        )
        try:
            self._scheduler.run()
        finally:
            logger.info("Lumina 服务已安全停止")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lumina A 股智能监控与研究系统")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("LUMINA_CONFIG", "config/lumina.yaml")),
        help="YAML 配置文件路径",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口，返回适合 systemd 判断的退出码。"""

    args = _build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Lumina 配置错误：{exc}", file=sys.stderr)
        return 2

    configure_logging(config.logging)
    try:
        LuminaService(config).run()
    except Exception:
        logger.exception("Lumina 服务异常退出")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
