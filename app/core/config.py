"""Lumina 双 YAML 配置加载与严格校验。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


class ConfigError(ValueError):
    """配置文件缺失、格式错误或字段非法。"""


@dataclass(frozen=True)
class AppSettings:
    """应用元数据与时区配置。"""

    name: str
    version: str
    timezone: str


@dataclass(frozen=True)
class RuntimeSettings:
    """服务运行参数。"""

    interval: float
    log_level: str


@dataclass(frozen=True)
class StorageSettings:
    """持久化配置。"""

    type: str
    path: Path
    busy_timeout_seconds: float = 10.0


@dataclass(frozen=True)
class WeChatSettings:
    """企业微信通知开关。"""

    enabled: bool


@dataclass(frozen=True)
class NotifySettings:
    """通知配置。"""

    wechat: WeChatSettings


@dataclass(frozen=True)
class StockSettings:
    """单个监控标的配置。"""

    code: str
    name: str
    type: str
    enabled: bool


@dataclass(frozen=True)
class AppConfig:
    """合并 settings.yaml 与 stocks.yaml 后的完整配置。"""

    app: AppSettings
    runtime: RuntimeSettings
    storage: StorageSettings
    notify: NotifySettings
    stocks: tuple[StockSettings, ...]


def _load_yaml(path: Path) -> Mapping[str, object]:
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在：{path}") from exc
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件：{path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 格式错误：{path}") from exc
    return _as_mapping(raw, str(path))


def _as_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"配置项 {field} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"配置项 {field} 的键必须是字符串")
    return value


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


def _positive_number(values: Mapping[str, object], key: str, field: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"配置项 {field} 必须是数字")
    result = float(value)
    if result <= 0:
        raise ConfigError(f"配置项 {field} 必须大于 0")
    return result


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
    return RuntimeSettings(
        interval=_positive_number(values, "interval", "runtime.interval"),
        log_level=log_level,
    )


def _parse_storage(root: Mapping[str, object]) -> StorageSettings:
    values = _required_mapping(root, "storage")
    storage_type = _required_string(values, "type", "storage.type").lower()
    if storage_type != "sqlite":
        raise ConfigError("当前仅支持 storage.type=sqlite")
    return StorageSettings(
        type=storage_type,
        path=Path(_required_string(values, "path", "storage.path")),
    )


def _parse_notify(root: Mapping[str, object]) -> NotifySettings:
    values = _required_mapping(root, "notify")
    wechat = _required_mapping(values, "wechat")
    return NotifySettings(
        wechat=WeChatSettings(enabled=_required_bool(wechat, "enabled", "notify.wechat.enabled"))
    )


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
    return tuple(stocks)


def load_config(settings_path: Path, stocks_path: Path) -> AppConfig:
    """加载两个配置文件，并在启动前完成字段和跨文件校验。"""

    settings_root = _load_yaml(settings_path)
    stocks_root = _load_yaml(stocks_path)
    return AppConfig(
        app=_parse_app(settings_root),
        runtime=_parse_runtime(settings_root),
        storage=_parse_storage(settings_root),
        notify=_parse_notify(settings_root),
        stocks=_parse_stocks(stocks_root),
    )
