"""Lumina 三份 YAML 配置的加载与严格校验。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import ConfigError as ConfigError
from app.core.market_config import MarketSettings as MarketSettings
from app.core.market_config import MockSettings as MockSettings
from app.core.market_config import parse_market
from app.core.notify_config import NotifySettings, parse_notify
from app.core.rule_config import load_rule_definitions
from app.core.yaml_loader import as_mapping as _as_mapping
from app.core.yaml_loader import load_yaml as _load_yaml
from app.monitor.model import RuleDefinition


@dataclass(frozen=True)
class AppSettings:
    """应用元数据与时区配置。"""

    name: str
    version: str
    timezone: str


@dataclass(frozen=True)
class RuntimeSettings:
    """服务运行参数。"""

    log_level: str


@dataclass(frozen=True)
class RetentionSettings:
    """SQLite 行情保留策略。"""

    quote_days: int = 30
    delete_batch_size: int = 5_000


@dataclass(frozen=True)
class BackupSettings:
    """SQLite 在线备份策略。"""

    directory: Path = Path("data/backups")
    keep_count: int = 14


@dataclass(frozen=True)
class StorageSettings:
    """持久化配置。"""

    type: str
    path: Path
    busy_timeout_seconds: float = 10.0
    retention: RetentionSettings = RetentionSettings()
    backup: BackupSettings = BackupSettings()


@dataclass(frozen=True)
class StockSettings:
    """单个监控标的配置。"""

    code: str
    name: str
    type: str
    enabled: bool


@dataclass(frozen=True)
class AppConfig:
    """合并 settings.yaml、stocks.yaml 与 rules.yaml 后的完整配置。"""

    app: AppSettings
    runtime: RuntimeSettings
    market: MarketSettings
    storage: StorageSettings
    notify: NotifySettings
    stocks: tuple[StockSettings, ...]
    rules: tuple[RuleDefinition, ...]


def _required_mapping(root: Mapping[str, object], key: str) -> Mapping[str, object]:
    if key not in root:
        raise ConfigError(f"缺少配置项：{key}")
    return _as_mapping(root[key], key)


def _required_string(values: Mapping[str, object], key: str, field: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {field} 必须是非空字符串")
    return value.strip()


def _required_bool(values: Mapping[str, object], key: str, field: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"配置项 {field} 必须是布尔值")
    return value


def _parse_app(root: Mapping[str, object]) -> AppSettings:
    values = _required_mapping(root, "app")
    name = _required_string(values, "name", "app.name")
    if name != "lumina":
        raise ConfigError("配置项 app.name 必须为 lumina")

    timezone_name = _required_string(values, "timezone", "app.timezone")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"无效时区：{timezone_name}") from exc

    return AppSettings(
        name=name,
        version=_required_string(values, "version", "app.version"),
        timezone=timezone_name,
    )


def _parse_runtime(root: Mapping[str, object]) -> RuntimeSettings:
    values = _required_mapping(root, "runtime")
    log_level = _required_string(values, "log_level", "runtime.log_level").upper()
    if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        raise ConfigError("配置项 runtime.log_level 非法")
    return RuntimeSettings(log_level=log_level)


def _parse_storage(root: Mapping[str, object]) -> StorageSettings:
    values = _required_mapping(root, "storage")
    storage_type = _required_string(values, "type", "storage.type").lower()
    if storage_type != "sqlite":
        raise ConfigError("当前仅支持 storage.type=sqlite")
    retention_values = values.get("retention", {})
    retention = _as_mapping(retention_values, "storage.retention")
    quote_days = _positive_int(retention, "quote_days", "storage.retention.quote_days", 30)
    batch_size = _positive_int(
        retention,
        "delete_batch_size",
        "storage.retention.delete_batch_size",
        5_000,
    )

    backup_values = values.get("backup", {})
    backup = _as_mapping(backup_values, "storage.backup")
    backup_directory = backup.get("directory", "data/backups")
    if not isinstance(backup_directory, str) or not backup_directory.strip():
        raise ConfigError("配置项 storage.backup.directory 必须是非空字符串")

    return StorageSettings(
        type=storage_type,
        path=Path(_required_string(values, "path", "storage.path")),
        retention=RetentionSettings(quote_days=quote_days, delete_batch_size=batch_size),
        backup=BackupSettings(
            directory=Path(backup_directory.strip()),
            keep_count=_positive_int(backup, "keep_count", "storage.backup.keep_count", 14),
        ),
    )


def _positive_int(
    values: Mapping[str, object],
    key: str,
    field: str,
    default: int,
) -> int:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"配置项 {field} 必须是大于 0 的整数")
    return value


def _normalize_stock_code(value: object, index: int) -> str:
    field = f"stocks[{index}].code"
    if isinstance(value, bool):
        raise ConfigError(f"配置项 {field} 必须是 6 位证券代码")
    if isinstance(value, int):
        code = f"{value:06d}"
    elif isinstance(value, str):
        code = value.strip()
    else:
        raise ConfigError(f"配置项 {field} 必须是字符串或整数")
    if len(code) != 6 or not code.isdigit():
        raise ConfigError(f"配置项 {field} 必须是 6 位证券代码")
    return code


def _parse_stocks(root: Mapping[str, object]) -> tuple[StockSettings, ...]:
    raw_stocks = root.get("stocks")
    if not isinstance(raw_stocks, list):
        raise ConfigError("配置项 stocks 必须是列表")

    stocks: list[StockSettings] = []
    seen_codes: set[str] = set()
    for index, raw_stock in enumerate(raw_stocks):
        values = _as_mapping(raw_stock, f"stocks[{index}]")
        code = _normalize_stock_code(values.get("code"), index)
        stock_type = _required_string(values, "type", f"stocks[{index}].type").upper()
        if stock_type not in {"ETF", "INDEX", "STOCK"}:
            raise ConfigError(f"配置项 stocks[{index}].type 非法")
        if code in seen_codes:
            raise ConfigError(f"股票代码重复：{code}")
        seen_codes.add(code)
        stocks.append(
            StockSettings(
                code=code,
                name=_required_string(values, "name", f"stocks[{index}].name"),
                type=stock_type,
                enabled=_required_bool(values, "enabled", f"stocks[{index}].enabled"),
            )
        )
    if not any(stock.enabled for stock in stocks):
        raise ConfigError("stocks.yaml 中没有 enabled: true 的监控标的")
    return tuple(stocks)


def load_config(
    settings_path: Path,
    stocks_path: Path,
    rules_path: Path,
) -> AppConfig:
    """加载三个配置文件，并在启动前完成字段和跨文件校验。"""

    settings_root = _load_yaml(settings_path)
    stocks_root = _load_yaml(stocks_path)
    stocks = _parse_stocks(stocks_root)
    return AppConfig(
        app=_parse_app(settings_root),
        runtime=_parse_runtime(settings_root),
        market=parse_market(settings_root),
        storage=_parse_storage(settings_root),
        notify=parse_notify(settings_root),
        stocks=stocks,
        rules=load_rule_definitions(
            rules_path,
            frozenset(stock.code for stock in stocks),
        ),
    )
