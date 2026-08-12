from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import MarketSettings, MockSettings
from app.core.market_config import TencentSettings
from app.market.factory import MarketSourceCreationError, create_market_source
from app.market.mock import MockMarketSource
from app.market.tencent import TencentMarketSource


def _settings(source: str, seed: int | None = 42) -> MarketSettings:
    tencent = None
    if source == "tencent":
        tencent = TencentSettings(
            url="https://qt.gtimg.cn/q=",
            timeout_seconds=3,
            batch_size=50,
            max_attempts=2,
            retry_backoff_seconds=0,
            max_total_seconds=8,
        )
    return MarketSettings(
        source=source,
        interval_seconds=5,
        mock=MockSettings(seed=seed),
        tencent=tencent,
    )


def test_factory_selects_mock_market_source() -> None:
    fixed_time = datetime(2026, 7, 31, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    source = create_market_source(
        _settings("mock"),
        mock_clock=lambda: fixed_time,
    )

    assert isinstance(source, MockMarketSource)
    assert source.name == "mock"


def test_factory_creates_tencent_market_source() -> None:
    source = create_market_source(_settings("tencent"))

    assert isinstance(source, TencentMarketSource)
    assert source.name == "tencent"


def test_factory_defensively_rejects_missing_tencent_config() -> None:
    settings = MarketSettings(
        source="tencent",
        interval_seconds=5,
        mock=MockSettings(seed=42),
        tencent=None,
    )

    with pytest.raises(MarketSourceCreationError, match="缺少有效配置"):
        create_market_source(settings)


def test_factory_rejects_unimplemented_sina_source() -> None:
    with pytest.raises(MarketSourceCreationError, match="sina 尚未实现"):
        create_market_source(_settings("sina"))


def test_factory_defensively_rejects_unknown_source() -> None:
    with pytest.raises(MarketSourceCreationError, match="未知行情源"):
        create_market_source(_settings("unknown"))
