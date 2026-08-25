from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.core.config import AppConfig, load_config
from app.preflight import run_preflight


def test_preflight_checks_directories_and_sqlite_without_network(tmp_path: Path) -> None:
    base = load_config(
        Path("config/settings.yaml"),
        Path("config/stocks.yaml"),
        Path("config/rules.yaml"),
    )
    config = AppConfig(
        app=base.app,
        runtime=base.runtime,
        market=base.market,
        storage=replace(
            base.storage,
            path=tmp_path / "data/lumina.db",
        ),
        notify=base.notify,
        stocks=base.stocks,
        rules=base.rules,
    )

    run_preflight(config, tmp_path / "logs")

    assert config.storage.path.exists()
    assert (tmp_path / "logs").is_dir()
