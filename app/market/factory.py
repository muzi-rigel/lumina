"""根据配置创建行情源实例。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal

from app.core.config import MarketSettings
from app.market.mock import MockMarketSource
from app.market.source import MarketSource


class MarketSourceCreationError(RuntimeError):
    """行情源无法在启动阶段完成创建。"""


def create_market_source(
    settings: MarketSettings,
    *,
    mock_clock: Callable[[], datetime] | None = None,
    mock_initial_prices: Mapping[str, Decimal] | None = None,
    mock_failure_codes: set[str] | None = None,
) -> MarketSource:
    """创建配置指定的行情源，不允许静默回退。"""

    if settings.source == "mock":
        return MockMarketSource(
            initial_prices=mock_initial_prices,
            failure_codes=mock_failure_codes,
            clock=mock_clock,
            seed=settings.mock.seed,
        )
    if settings.source in {"sina", "tencent"}:
        raise MarketSourceCreationError(f"行情源 {settings.source} 尚未实现")
    raise MarketSourceCreationError(f"未知行情源：{settings.source}")
