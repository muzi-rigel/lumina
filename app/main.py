"""Lumina 服务启动入口。"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from types import FrameType
from zoneinfo import ZoneInfo

from app.core.config import AppConfig, ConfigError, load_config
from app.core.logger import configure_logging
from app.core.scheduler import IntervalScheduler
from app.storage.sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


class StartupError(RuntimeError):
    """启动环境不满足服务运行要求。"""


def _ensure_directory(path: Path, label: str) -> None:
    """建立运行目录，并确认目标确实为目录。"""

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StartupError(f"无法创建{label}：{path}") from exc
    if not path.is_dir():
        raise StartupError(f"{label}不是有效目录：{path}")


def _run_startup_checks(
    config: AppConfig,
    settings_path: Path,
    stocks_path: Path,
    log_dir: Path,
) -> None:
    """执行不会访问外部网络的启动自检。"""

    logger.info("✔ 配置文件存在：%s, %s", settings_path, stocks_path)
    logger.info("✔ 日志目录存在：%s", log_dir)

    data_dir = config.storage.path.parent
    _ensure_directory(data_dir, "数据目录")
    logger.info("✔ 数据目录存在：%s", data_dir)

    local_time = datetime.now(ZoneInfo(config.app.timezone))
    logger.info(
        "✔ 时间正常：%s (%s)",
        local_time.isoformat(timespec="seconds"),
        config.app.timezone,
    )


class LuminaService:
    """装配基础设施并管理服务生命周期。"""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._scheduler = IntervalScheduler(config.runtime.interval)
        self._storage = SQLiteStorage(
            config.storage.path,
            config.storage.busy_timeout_seconds,
        )
        self._stopping = False

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        del frame
        if self._stopping:
            return
        self._stopping = True
        logger.info("收到停止信号，准备优雅退出，signal=%s", signal.Signals(signum).name)
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

        enabled_count = sum(stock.enabled for stock in self._config.stocks)
        logger.info(
            "Lumina %s 服务启动，监控标的=%d database=%s",
            self._config.app.version,
            enabled_count,
            self._config.storage.path,
        )
        try:
            self._scheduler.run()
        finally:
            logger.info("Lumina 服务已安全停止")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lumina A 股智能监控与研究系统")
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path(os.environ.get("LUMINA_SETTINGS", "config/settings.yaml")),
        help="settings.yaml 路径",
    )
    parser.add_argument(
        "--stocks",
        type=Path,
        default=Path(os.environ.get("LUMINA_STOCKS", "config/stocks.yaml")),
        help="stocks.yaml 路径",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口，返回适合 systemd 判断的退出码。"""

    args = _build_parser().parse_args(argv)
    log_dir = Path(os.environ.get("LUMINA_LOG_DIR", "logs"))
    try:
        config = load_config(args.settings, args.stocks)
        _ensure_directory(log_dir, "日志目录")
        configure_logging(config.runtime.log_level, log_dir / "lumina.log")
        _run_startup_checks(config, args.settings, args.stocks, log_dir)
        LuminaService(config).run()
    except (ConfigError, StartupError) as exc:
        print(f"Lumina 启动失败：{exc}", file=sys.stderr)
        return 2
    except Exception:
        logger.exception("Lumina 服务异常退出")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
