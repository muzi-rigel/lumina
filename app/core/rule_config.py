"""rules.yaml 的类型化加载与严格校验。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TypeVar

from app.core.errors import ConfigError
from app.core.yaml_loader import as_mapping, load_yaml
from app.market.model import InstrumentType
from app.monitor.model import (
    AlertSeverity,
    RuleDefinition,
    RuleDirection,
    RuleTargets,
    RuleType,
)

RULE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RULE_FIELDS = {
    "id",
    "name",
    "type",
    "enabled",
    "direction",
    "threshold",
    "window_seconds",
    "severity",
    "cooldown_seconds",
    "targets",
}
EnumT = TypeVar("EnumT", RuleType, RuleDirection, AlertSeverity, InstrumentType)


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


def _enum_value(
    enum_type: type[EnumT],
    value: str,
    field: str,
) -> EnumT:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ConfigError(f"配置项 {field} 的值未知：{value}") from exc


def _parse_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise ConfigError(f"配置项 {field} 必须是十进制数值")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ConfigError(f"配置项 {field} 不是有效 Decimal") from exc
    if not result.is_finite() or result <= 0:
        raise ConfigError(f"配置项 {field} 必须是大于 0 的有限 Decimal")
    return result


def _parse_non_negative_int(values: Mapping[str, object], key: str, field: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"配置项 {field} 必须是非负整数")
    return value


def _parse_string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"配置项 {field} 必须是非空列表")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ConfigError(f"配置项 {field} 必须只包含非空字符串")
    result = tuple(item.strip() for item in value)
    if len(set(result)) != len(result):
        raise ConfigError(f"配置项 {field} 包含重复值")
    return result


def _parse_targets(
    value: object,
    field: str,
    valid_codes: frozenset[str],
) -> RuleTargets:
    if value is None:
        return RuleTargets()
    values = as_mapping(value, field)
    unknown_keys = set(values) - {"codes", "instrument_types"}
    if unknown_keys:
        raise ConfigError(f"配置项 {field} 包含未知字段：{sorted(unknown_keys)}")
    if "codes" in values and "instrument_types" in values:
        raise ConfigError(f"配置项 {field} 只能配置 codes 或 instrument_types 其中一种")
    if "codes" in values:
        codes = _parse_string_list(values["codes"], f"{field}.codes")
        missing = sorted(set(codes) - valid_codes)
        if missing:
            raise ConfigError(f"配置项 {field}.codes 引用了不存在的证券代码：{missing}")
        return RuleTargets(codes=frozenset(codes))
    if "instrument_types" in values:
        raw_types = _parse_string_list(
            values["instrument_types"],
            f"{field}.instrument_types",
        )
        instrument_types = frozenset(
            _enum_value(InstrumentType, item.upper(), f"{field}.instrument_types")
            for item in raw_types
        )
        return RuleTargets(instrument_types=instrument_types)
    raise ConfigError(f"配置项 {field} 必须配置 codes 或 instrument_types")


def _parse_window_seconds(
    values: Mapping[str, object],
    rule_type: RuleType,
    field: str,
) -> int | None:
    if rule_type is RuleType.DAY_CHANGE_PERCENT:
        if "window_seconds" in values:
            raise ConfigError(f"日内规则 {field} 不允许配置 window_seconds")
        return None
    value = values.get("window_seconds")
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 86_400:
        raise ConfigError(f"窗口规则 {field}.window_seconds 必须是 1 到 86400 的整数")
    return value


def _parse_rule(
    values: Mapping[str, object],
    index: int,
    valid_codes: frozenset[str],
) -> RuleDefinition:
    field = f"rules[{index}]"
    unknown_keys = set(values) - RULE_FIELDS
    if unknown_keys:
        raise ConfigError(f"配置项 {field} 包含未知字段：{sorted(unknown_keys)}")
    rule_id = _required_string(values, "id", f"{field}.id")
    if not RULE_ID_PATTERN.fullmatch(rule_id):
        raise ConfigError(f"配置项 {field}.id 格式非法")
    rule_type = _enum_value(
        RuleType,
        _required_string(values, "type", f"{field}.type").upper(),
        f"{field}.type",
    )
    direction = _enum_value(
        RuleDirection,
        _required_string(values, "direction", f"{field}.direction").upper(),
        f"{field}.direction",
    )
    threshold = _parse_decimal(values.get("threshold"), f"{field}.threshold")
    if direction is RuleDirection.FALL and threshold > Decimal("100"):
        raise ConfigError(f"配置项 {field}.threshold 的下跌幅度不能超过 100")
    severity = _enum_value(
        AlertSeverity,
        _required_string(values, "severity", f"{field}.severity").upper(),
        f"{field}.severity",
    )
    return RuleDefinition(
        id=rule_id,
        name=_required_string(values, "name", f"{field}.name"),
        type=rule_type,
        enabled=_required_bool(values, "enabled", f"{field}.enabled"),
        direction=direction,
        threshold=threshold,
        severity=severity,
        cooldown_seconds=_parse_non_negative_int(
            values,
            "cooldown_seconds",
            f"{field}.cooldown_seconds",
        ),
        window_seconds=_parse_window_seconds(values, rule_type, field),
        targets=_parse_targets(values.get("targets"), f"{field}.targets", valid_codes),
    )


def load_rule_definitions(
    path: Path,
    valid_codes: frozenset[str],
) -> tuple[RuleDefinition, ...]:
    """加载规则，并校验全局 ID 唯一性和目标引用。"""

    root = load_yaml(path)
    raw_rules = root.get("rules")
    if not isinstance(raw_rules, list):
        raise ConfigError("配置项 rules 必须是列表")

    definitions: list[RuleDefinition] = []
    seen_ids: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        definition = _parse_rule(as_mapping(raw_rule, f"rules[{index}]"), index, valid_codes)
        if definition.id in seen_ids:
            raise ConfigError(f"规则 ID 重复：{definition.id}")
        seen_ids.add(definition.id)
        definitions.append(definition)
    return tuple(definitions)
