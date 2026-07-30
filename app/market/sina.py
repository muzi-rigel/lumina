"""新浪行情源占位实现。"""

from __future__ import annotations

from collections.abc import Sequence

from app.market.model import MarketInstrument
from app.market.source import MarketSource, MarketSourceError, QuoteBatch


class SinaMarketSource(MarketSource):
    """新浪行情接口骨架，暂不实现网络访问。"""

    @property
    def name(self) -> str:
        return "sina"

    def fetch_quotes(self, instruments: Sequence[MarketInstrument]) -> QuoteBatch:
        del instruments
        raise MarketSourceError("新浪行情源尚未实现")
