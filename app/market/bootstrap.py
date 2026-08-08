"""将应用配置装配为可调度的行情采集器。"""

from __future__ import annotations

from app.core.config import AppConfig
from app.market.collector import MarketCollector
from app.market.factory import create_market_source
from app.market.model import InstrumentType, MarketInstrument
from app.monitor.factory import build_monitor_engine


class MarketBootstrapError(RuntimeError):
    """行情采集依赖无法完成启动装配。"""


def build_market_collector(config: AppConfig) -> MarketCollector:
    """转换启用标的并装配行情源、监控引擎和采集器。"""

    instruments = tuple(
        MarketInstrument(
            code=stock.code,
            name=stock.name,
            type=InstrumentType(stock.type),
        )
        for stock in config.stocks
        if stock.enabled
    )
    if not instruments:
        raise MarketBootstrapError("没有启用的监控标的，拒绝启动空服务")

    return MarketCollector(
        source=create_market_source(config.market),
        instruments=instruments,
        monitor_engine=build_monitor_engine(
            definitions=config.rules,
            interval_seconds=config.market.interval_seconds,
            timezone_name=config.app.timezone,
        ),
    )
