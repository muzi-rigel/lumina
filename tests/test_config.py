from pathlib import Path

import pytest

from app.core.config import ConfigError, load_config

VALID_SETTINGS = """
app:
  name: lumina
  version: 0.1.0
  timezone: Asia/Shanghai
runtime:
  log_level: INFO
market:
  source: mock
  interval_seconds: 5
  mock:
    seed: 42
storage:
  type: sqlite
  path: data/lumina.db
notify:
  wechat:
    enabled: false
"""

VALID_STOCKS = """
stocks:
  - code: "510300"
    name: 沪深300ETF
    type: ETF
    enabled: true
  - code: 000001
    name: 上证指数
    type: INDEX
    enabled: true
"""


def _write_configs(tmp_path: Path) -> tuple[Path, Path]:
    settings_path = tmp_path / "settings.yaml"
    stocks_path = tmp_path / "stocks.yaml"
    settings_path.write_text(VALID_SETTINGS, encoding="utf-8")
    stocks_path.write_text(VALID_STOCKS, encoding="utf-8")
    return settings_path, stocks_path


def test_load_config_reads_and_merges_two_files(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)

    config = load_config(settings_path, stocks_path)

    assert config.app.name == "lumina"
    assert config.app.timezone == "Asia/Shanghai"
    assert config.runtime.log_level == "INFO"
    assert config.market.source == "mock"
    assert config.market.interval_seconds == 5
    assert config.market.mock.seed == 42
    assert config.storage.type == "sqlite"
    assert config.storage.path == Path("data/lumina.db")
    assert config.notify.wechat.enabled is False
    assert [stock.code for stock in config.stocks] == ["510300", "000001"]


def test_load_config_rejects_invalid_interval(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)
    settings_path.write_text(
        VALID_SETTINGS.replace("interval_seconds: 5", "interval_seconds: 0"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="必须大于 0"):
        load_config(settings_path, stocks_path)


def test_load_config_rejects_invalid_timezone(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)
    settings_path.write_text(
        VALID_SETTINGS.replace("Asia/Shanghai", "Invalid/Timezone"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="无效时区"):
        load_config(settings_path, stocks_path)


def test_load_config_reports_missing_stocks_file(tmp_path: Path) -> None:
    settings_path, _ = _write_configs(tmp_path)

    with pytest.raises(ConfigError, match="配置文件不存在"):
        load_config(settings_path, tmp_path / "missing.yaml")


def test_load_config_rejects_unknown_market_source(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)
    settings_path.write_text(
        VALID_SETTINGS.replace("source: mock", "source: unknown"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="不支持的行情源"):
        load_config(settings_path, stocks_path)


def test_load_config_rejects_non_integer_mock_seed(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)
    settings_path.write_text(
        VALID_SETTINGS.replace("seed: 42", "seed: 4.2"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="必须是整数或 null"):
        load_config(settings_path, stocks_path)


def test_load_config_accepts_null_mock_seed(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)
    settings_path.write_text(
        VALID_SETTINGS.replace("seed: 42", "seed: null"),
        encoding="utf-8",
    )

    config = load_config(settings_path, stocks_path)

    assert config.market.mock.seed is None


def test_load_config_rejects_empty_enabled_stocks(tmp_path: Path) -> None:
    settings_path, stocks_path = _write_configs(tmp_path)
    stocks_path.write_text(
        VALID_STOCKS.replace("enabled: true", "enabled: false"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="没有 enabled: true"):
        load_config(settings_path, stocks_path)
