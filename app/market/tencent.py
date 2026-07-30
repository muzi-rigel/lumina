"""腾讯行情源占位实现。"""

from __future__ import annotations

from collections.abc import Sequence

from app.market.source import MarketQuote, MarketSource, MarketSourceError


class TencentMarketSource(MarketSource):
    """腾讯行情接口骨架，暂不实现网络访问。"""

    @property
    def name(self) -> str:
        return "tencent"

    def fetch_quotes(self, symbols: Sequence[str]) -> list[MarketQuote]:
        del symbols
        raise MarketSourceError("腾讯行情源尚未实现")
