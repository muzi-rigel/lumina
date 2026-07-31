from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import MarketSettings, MockSettings
from app.market.factory import MarketSourceCreationError, create_market_source
from app.market.mock import MockMarketSource


def _settings(source: str, seed: int | None = 42) -> MarketSettings:
    return MarketSettings(
        source=source,
        interval_seconds=5,
        mock=MockSettings(seed=seed),
    )


def test_factory_selects_mock_market_source() -> None:
    fixed_time = datetime(2026, 7, 31, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    source = create_market_source(
        _settings("mock"),
        mock_clock=lambda: fixed_time,
    )

    assert isinstance(source, MockMarketSource)
    assert source.name == "mock"


@pytest.mark.parametrize("source_name", ["sina", "tencent"])
def test_factory_rejects_unimplemented_source(source_name: str) -> None:
    with pytest.raises(MarketSourceCreationError, match=f"{source_name} 尚未实现"):
        create_market_source(_settings(source_name))


def test_factory_defensively_rejects_unknown_source() -> None:
    with pytest.raises(MarketSourceCreationError, match="未知行情源"):
        create_market_source(_settings("unknown"))
