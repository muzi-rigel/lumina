from pathlib import Path

from app.core.config import load_config
from app.market.bootstrap import build_market_collector


def test_bootstrap_collects_only_enabled_stocks(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    stocks_path = tmp_path / "stocks.yaml"
    settings_path.write_text(
        Path("config/settings.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    stocks_path.write_text(
        """
stocks:
  - code: "510300"
    name: 沪深300ETF
    type: ETF
    enabled: true
  - code: "512480"
    name: 半导体ETF
    type: ETF
    enabled: false
""",
        encoding="utf-8",
    )
    config = load_config(settings_path, stocks_path)

    batch = build_market_collector(config).collect_once()

    assert batch is not None
    assert [quote.symbol for quote in batch.quotes] == ["510300"]
