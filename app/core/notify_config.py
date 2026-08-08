"""通知配置模型与严格校验。"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.core.errors import ConfigError
from app.core.yaml_loader import as_mapping

WECHAT_FIELDS = {
    "enabled",
    "webhook_env",
    "timeout_seconds",
    "max_attempts",
    "retry_backoff_seconds",
    "max_total_seconds",
}


@dataclass(frozen=True)
class WeChatSettings:
    """企业微信机器人参数，不直接保存 webhook 密钥。"""

    enabled: bool
    webhook_env: str
    timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float
    max_total_seconds: float


@dataclass(frozen=True)
class NotifySettings:
    wechat: WeChatSettings


def _number(value: object, field: str, *, allow_zero: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"配置项 {field} 必须是数字")
    result = float(value)
    lower_bound_valid = result >= 0 if allow_zero else result > 0
    if not math.isfinite(result) or not lower_bound_valid:
        qualifier = "非负" if allow_zero else "大于 0 的"
        raise ConfigError(f"配置项 {field} 必须是{qualifier}有限数值")
    return result


def _required_string(values: Mapping[str, object], key: str, field: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"配置项 {field} 必须是非空字符串")
    return value.strip()


def parse_notify(root: Mapping[str, object]) -> NotifySettings:
    """解析通知参数，并限制同步通知的单次资源占用。"""

    if "notify" not in root:
        raise ConfigError("缺少配置项：notify")
    notify = as_mapping(root["notify"], "notify")
    unknown_channels = set(notify) - {"wechat"}
    if unknown_channels:
        raise ConfigError(f"配置项 notify 包含未知字段：{sorted(unknown_channels)}")
    if "wechat" not in notify:
        raise ConfigError("缺少配置项：wechat")
    wechat = as_mapping(notify["wechat"], "notify.wechat")
    unknown_fields = set(wechat) - WECHAT_FIELDS
    if unknown_fields:
        raise ConfigError(f"配置项 notify.wechat 包含未知字段：{sorted(unknown_fields)}")

    enabled = wechat.get("enabled")
    if not isinstance(enabled, bool):
        raise ConfigError("配置项 notify.wechat.enabled 必须是布尔值")
    webhook_env = _required_string(wechat, "webhook_env", "notify.wechat.webhook_env")
    if re.fullmatch(r"[A-Z_][A-Z0-9_]*", webhook_env) is None:
        raise ConfigError("配置项 notify.wechat.webhook_env 必须是有效的环境变量名")
    attempts = wechat.get("max_attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 5:
        raise ConfigError("配置项 notify.wechat.max_attempts 必须是 1 到 5 的整数")

    return NotifySettings(
        wechat=WeChatSettings(
            enabled=enabled,
            webhook_env=webhook_env,
            timeout_seconds=_number(
                wechat.get("timeout_seconds"),
                "notify.wechat.timeout_seconds",
                allow_zero=False,
            ),
            max_attempts=attempts,
            retry_backoff_seconds=_number(
                wechat.get("retry_backoff_seconds"),
                "notify.wechat.retry_backoff_seconds",
                allow_zero=True,
            ),
            max_total_seconds=_number(
                wechat.get("max_total_seconds"),
                "notify.wechat.max_total_seconds",
                allow_zero=False,
            ),
        )
    )
