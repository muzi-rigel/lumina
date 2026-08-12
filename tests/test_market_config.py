from collections.abc import Mapping

import pytest

from app.core.errors import ConfigError
from app.core.market_config import parse_market


def _root(
    source: str = "tencent",
    *,
    include_tencent: bool = True,
    **tencent_overrides: object,
) -> Mapping[str, object]:
    market: dict[str, object] = {
        "source": source,
        "interval_seconds": 5,
        "mock": {"seed": 42},
    }
    if include_tencent:
        tencent: dict[str, object] = {
            "url": "https://qt.gtimg.cn/q=",
            "timeout_seconds": 3,
            "batch_size": 50,
            "max_attempts": 2,
            "retry_backoff_seconds": 0.5,
            "max_total_seconds": 8,
        }
        tencent.update(tencent_overrides)
        market["tencent"] = tencent
    return {"market": market}


def test_mock_source_does_not_require_tencent_config() -> None:
    settings = parse_market(_root("mock", include_tencent=False))

    assert settings.source == "mock"
    assert settings.mock.seed == 42
    assert settings.tencent is None


def test_mock_source_does_not_validate_unused_tencent_config() -> None:
    root = _root("mock", include_tencent=False)
    root["market"]["tencent"] = {"url": "not-a-url", "max_attempts": 0}  # type: ignore[index]

    settings = parse_market(root)

    assert settings.tencent is None


def test_tencent_source_loads_complete_config() -> None:
    settings = parse_market(_root())

    assert settings.source == "tencent"
    assert settings.tencent is not None
    assert settings.tencent.url == "https://qt.gtimg.cn/q="
    assert settings.tencent.timeout_seconds == 3
    assert settings.tencent.batch_size == 50
    assert settings.tencent.max_attempts == 2
    assert settings.tencent.retry_backoff_seconds == 0.5
    assert settings.tencent.max_total_seconds == 8


def test_tencent_source_requires_config_block() -> None:
    with pytest.raises(ConfigError, match="缺少配置项：market.tencent"):
        parse_market(_root(include_tencent=False))


@pytest.mark.parametrize(
    "url",
    ["", "http://qt.gtimg.cn/q=", "https://user:secret@qt.gtimg.cn/q=", "https://x/#bad"],
)
def test_tencent_source_rejects_invalid_url(url: str) -> None:
    with pytest.raises(ConfigError, match="HTTPS URL"):
        parse_market(_root(url=url))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("timeout_seconds", 0, "大于 0"),
        ("timeout_seconds", float("inf"), "有限数值"),
        ("batch_size", 0, "1 到 50"),
        ("batch_size", 51, "1 到 50"),
        ("max_attempts", 0, "1 到 5"),
        ("max_attempts", 6, "1 到 5"),
        ("retry_backoff_seconds", -1, "非负有限数值"),
        ("max_total_seconds", 0, "大于 0"),
    ],
)
def test_tencent_source_rejects_invalid_runtime_config(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_market(_root(**{field: value}))


def test_tencent_source_rejects_unknown_field() -> None:
    with pytest.raises(ConfigError, match="未知字段"):
        parse_market(_root(retries=2))


def test_market_config_rejects_unknown_source() -> None:
    with pytest.raises(ConfigError, match="不支持的行情源"):
        parse_market(_root("unknown", include_tencent=False))
