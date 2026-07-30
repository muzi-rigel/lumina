"""Lumina YAML 配置加载与校验。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """配置文件缺失、格式错误或字段非法。"""


@dataclass(frozen=True)
class SchedulerConfig:
    """周期调度配置。"""

    interval_seconds: float = 30.0


@dataclass(frozen=True)
class LoggingConfig:
    """标准日志配置。"""

    level: str = "INFO"
    file_path: Path | None = None
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 10


@dataclass(frozen=True)
class StorageConfig:
    """SQLite 存储配置。"""

    database_path: Path = Path("data/lumina.db")
    busy_timeout_seconds: float = 10.0


@dataclass(frozen=True)
class AppConfig:
    """应用完整配置。"""

    scheduler: SchedulerConfig
    logging: LoggingConfig
    storage: StorageConfig


def _as_mapping(value: object, field: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"配置项 {field} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"配置项 {field} 的键必须是字符串")
    return value


def _positive_number(
    values: Mapping[str, object],
    key: str,
    default: float,
    field: str,
) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"配置项 {field} 必须是数字")
    result = float(value)
    if result <= 0:
        raise ConfigError(f"配置项 {field} 必须大于 0")
    return result


def _positive_int(
    values: Mapping[str, object],
    key: str,
    default: int,
    field: str,
) -> int:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"配置项 {field} 必须是整数")
    if value <= 0:
        raise ConfigError(f"配置项 {field} 必须大于 0")
    return value


def _parse_scheduler(root: Mapping[str, object]) -> SchedulerConfig:
    values = _as_mapping(root.get("scheduler"), "scheduler")
    return SchedulerConfig(
        interval_seconds=_positive_number(
            values,
            "interval_seconds",
            30.0,
            "scheduler.interval_seconds",
        )
    )


def _parse_logging(root: Mapping[str, object]) -> LoggingConfig:
    values = _as_mapping(root.get("logging"), "logging")
    level = values.get("level", "INFO")
    if not isinstance(level, str) or level.upper() not in {
        "CRITICAL",
        "ERROR",
        "WARNING",
        "INFO",
        "DEBUG",
    }:
        raise ConfigError("配置项 logging.level 非法")

    file_value = values.get("file")
    if file_value is not None and not isinstance(file_value, str):
        raise ConfigError("配置项 logging.file 必须是字符串或 null")

    return LoggingConfig(
        level=level.upper(),
        file_path=Path(file_value) if file_value else None,
        max_bytes=_positive_int(
            values,
            "max_bytes",
            10 * 1024 * 1024,
            "logging.max_bytes",
        ),
        backup_count=_positive_int(
            values,
            "backup_count",
            10,
            "logging.backup_count",
        ),
    )


def _parse_storage(root: Mapping[str, object]) -> StorageConfig:
    values = _as_mapping(root.get("storage"), "storage")
    path_value = values.get("database", "data/lumina.db")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ConfigError("配置项 storage.database 必须是非空字符串")

    return StorageConfig(
        database_path=Path(path_value),
        busy_timeout_seconds=_positive_number(
            values,
            "busy_timeout_seconds",
            10.0,
            "storage.busy_timeout_seconds",
        ),
    )


def load_config(path: Path) -> AppConfig:
    """读取 YAML 并在服务启动前完成严格校验。"""

    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在：{path}") from exc
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件：{path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 格式错误：{path}") from exc

    root = _as_mapping(raw, "root")
    return AppConfig(
        scheduler=_parse_scheduler(root),
        logging=_parse_logging(root),
        storage=_parse_storage(root),
    )
