"""行情源配置模型与严格校验。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.errors import ConfigError
from app.core.yaml_loader import as_mapping

MARKET_FIELDS = {"source", "interval_seconds", "mock", "tencent"}
MOCK_FIELDS = {"seed"}
TENCENT_FIELDS = {
    "url",
    "timeout_seconds",
    "batch_size",
    "max_attempts",
    "retry_backoff_seconds",
    "max_total_seconds",
}


@dataclass(frozen=True)
class MockSettings:
    seed: int | None


@dataclass(frozen=True)
class TencentSettings:
    url: str
    timeout_seconds: float
    batch_size: int
    max_attempts: int
    retry_backoff_seconds: float
    max_total_seconds: float


@dataclass(frozen=True)
class MarketSettings:
    source: str
    interval_seconds: float
    mock: MockSettings
    tencent: TencentSettings | None


def _number(value: object, field: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"配置项 {field} 必须是数字")
    result = float(value)
    valid = result >= 0 if allow_zero else result > 0
    if not math.isfinite(result) or not valid:
        qualifier = "非负" if allow_zero else "大于 0 的"
        raise ConfigError(f"配置项 {field} 必须是{qualifier}有限数值")
    return result


def _https_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ConfigError("配置项 market.tencent.url 必须是有效 HTTPS URL")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ConfigError("配置项 market.tencent.url 必须是有效 HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ConfigError("配置项 market.tencent.url 必须是有效 HTTPS URL")
    return value


def _parse_tencent(values: Mapping[str, object]) -> TencentSettings:
    if "tencent" not in values:
        raise ConfigError("market.source=tencent 时缺少配置项：market.tencent")
    raw = as_mapping(values["tencent"], "market.tencent")
    unknown_fields = set(raw) - TENCENT_FIELDS
    if unknown_fields:
        raise ConfigError(f"配置项 market.tencent 包含未知字段：{sorted(unknown_fields)}")
    attempts = raw.get("max_attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 5:
        raise ConfigError("配置项 market.tencent.max_attempts 必须是 1 到 5 的整数")
    batch_size = raw.get("batch_size")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 50:
        raise ConfigError("配置项 market.tencent.batch_size 必须是 1 到 50 的整数")
    return TencentSettings(
        url=_https_url(raw.get("url")),
        timeout_seconds=_number(raw.get("timeout_seconds"), "market.tencent.timeout_seconds"),
        batch_size=batch_size,
        max_attempts=attempts,
        retry_backoff_seconds=_number(
            raw.get("retry_backoff_seconds"),
            "market.tencent.retry_backoff_seconds",
            allow_zero=True,
        ),
        max_total_seconds=_number(
            raw.get("max_total_seconds"),
            "market.tencent.max_total_seconds",
        ),
    )


def parse_market(root: Mapping[str, object]) -> MarketSettings:
    """解析 Mock 和腾讯行情配置，不允许未知行情源。"""

    if "market" not in root:
        raise ConfigError("缺少配置项：market")
    values = as_mapping(root["market"], "market")
    unknown_fields = set(values) - MARKET_FIELDS
    if unknown_fields:
        raise ConfigError(f"配置项 market 包含未知字段：{sorted(unknown_fields)}")
    source = values.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ConfigError("配置项 market.source 必须是非空字符串")
    source = source.strip().lower()
    if source not in {"mock", "sina", "tencent"}:
        raise ConfigError(f"不支持的行情源：{source}")

    seed: int | None = None
    if source == "mock":
        mock = as_mapping(values.get("mock", {}), "market.mock")
        unknown_mock_fields = set(mock) - MOCK_FIELDS
        if unknown_mock_fields:
            raise ConfigError(f"配置项 market.mock 包含未知字段：{sorted(unknown_mock_fields)}")
        raw_seed = mock.get("seed")
        if raw_seed is None:
            seed = None
        elif isinstance(raw_seed, int) and not isinstance(raw_seed, bool):
            seed = raw_seed
        else:
            raise ConfigError("配置项 market.mock.seed 必须是整数或 null")
    return MarketSettings(
        source=source,
        interval_seconds=_number(values.get("interval_seconds"), "market.interval_seconds"),
        mock=MockSettings(seed=seed),
        tencent=_parse_tencent(values) if source == "tencent" else None,
    )
