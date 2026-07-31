import signal
from pathlib import Path

import pytest

from app.core.config import load_config
from app.main import LuminaService, _ensure_directory, _run_startup_checks, main
from app.market.bootstrap import build_market_collector


def test_ensure_directory_creates_missing_path(tmp_path: Path) -> None:
    directory = tmp_path / "runtime" / "logs"

    _ensure_directory(directory, "日志目录")

    assert directory.is_dir()


def test_startup_checks_create_data_directory(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    stocks_path = tmp_path / "stocks.yaml"
    settings_path.write_text(
        f"""
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
  path: {tmp_path / "data" / "lumina.db"}
notify:
  wechat:
    enabled: false
""",
        encoding="utf-8",
    )
    stocks_path.write_text(
        """
stocks:
  - code: "510300"
    name: 沪深300ETF
    type: ETF
    enabled: true
""",
        encoding="utf-8",
    )
    config = load_config(settings_path, stocks_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    _run_startup_checks(config, settings_path, stocks_path, log_dir)

    assert config.storage.path.parent.is_dir()


def test_graceful_exit_is_idempotent(tmp_path: Path) -> None:
    settings_path = Path("config/settings.yaml")
    stocks_path = Path("config/stocks.yaml")
    config = load_config(settings_path, stocks_path)
    service = LuminaService(config, build_market_collector(config))

    service._handle_signal(signal.SIGTERM, None)
    service._handle_signal(signal.SIGTERM, None)

    assert service._stopping is True


@pytest.mark.parametrize("source_name", ["sina", "tencent"])
def test_main_rejects_unimplemented_market_source(
    source_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "settings.yaml"
    stocks_path = tmp_path / "stocks.yaml"
    settings_text = Path("config/settings.yaml").read_text(encoding="utf-8")
    settings_path.write_text(
        settings_text.replace("source: mock", f"source: {source_name}"),
        encoding="utf-8",
    )
    stocks_path.write_text(
        Path("config/stocks.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("LUMINA_LOG_DIR", str(tmp_path / "logs"))

    exit_code = main(
        [
            "--settings",
            str(settings_path),
            "--stocks",
            str(stocks_path),
        ]
    )

    assert exit_code == 2
    assert f"行情源 {source_name} 尚未实现" in capsys.readouterr().err
