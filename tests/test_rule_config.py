from pathlib import Path

import pytest

from app.core.config import ConfigError
from app.core.rule_config import load_rule_definitions
from app.monitor.model import RuleDirection, RuleType

VALID_CODES = frozenset({"510300", "000001"})


def _write_rules(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _valid_rule(extra: str = "") -> str:
    return f"""
rules:
  - id: day-rise
    name: 日内上涨
    type: DAY_CHANGE_PERCENT
    enabled: true
    direction: RISE
    threshold: "3.0"
    severity: WARNING
    cooldown_seconds: 60
{extra}
"""


def test_loads_valid_positive_magnitude_rule(tmp_path: Path) -> None:
    definitions = load_rule_definitions(_write_rules(tmp_path, _valid_rule()), VALID_CODES)

    assert len(definitions) == 1
    assert definitions[0].type is RuleType.DAY_CHANGE_PERCENT
    assert definitions[0].direction is RuleDirection.RISE
    assert str(definitions[0].threshold) == "3.0"


def test_duplicate_rule_id_rejected(tmp_path: Path) -> None:
    body = (
        _valid_rule()
        + """
  - id: day-rise
    name: 重复规则
    type: DAY_CHANGE_PERCENT
    enabled: true
    direction: FALL
    threshold: "3"
    severity: INFO
    cooldown_seconds: 0
"""
    )
    with pytest.raises(ConfigError, match="规则 ID 重复"):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("type: DAY_CHANGE_PERCENT", "type: UNKNOWN", "值未知"),
        ("direction: RISE", "direction: SIDEWAYS", "值未知"),
        ('threshold: "3.0"', 'threshold: "0"', "大于 0"),
        ('threshold: "3.0"', 'threshold: "NaN"', "有限 Decimal"),
        ('threshold: "3.0"', 'threshold: "Infinity"', "有限 Decimal"),
        ("cooldown_seconds: 60", "cooldown_seconds: -1", "非负整数"),
    ],
)
def test_invalid_rule_value_rejected(
    tmp_path: Path,
    old: str,
    new: str,
    message: str,
) -> None:
    body = _valid_rule().replace(old, new)
    with pytest.raises(ConfigError, match=message):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)


def test_window_rule_requires_window_seconds(tmp_path: Path) -> None:
    body = _valid_rule().replace("DAY_CHANGE_PERCENT", "WINDOW_CHANGE_PERCENT")
    with pytest.raises(ConfigError, match="window_seconds"):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)


def test_day_rule_rejects_window_seconds(tmp_path: Path) -> None:
    body = _valid_rule("    window_seconds: 300")
    with pytest.raises(ConfigError, match="不允许配置 window_seconds"):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)


def test_fall_threshold_cannot_exceed_one_hundred(tmp_path: Path) -> None:
    body = _valid_rule().replace("direction: RISE", "direction: FALL")
    body = body.replace('threshold: "3.0"', 'threshold: "100.01"')
    with pytest.raises(ConfigError, match="不能超过 100"):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)


def test_targets_cannot_mix_codes_and_types(tmp_path: Path) -> None:
    body = _valid_rule(
        """    targets:
      codes: ["510300"]
      instrument_types: [ETF]"""
    )
    with pytest.raises(ConfigError, match="只能配置"):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)


def test_targets_reject_unknown_code(tmp_path: Path) -> None:
    body = _valid_rule('    targets:\n      codes: ["999999"]')
    with pytest.raises(ConfigError, match="不存在的证券代码"):
        load_rule_definitions(_write_rules(tmp_path, body), VALID_CODES)
