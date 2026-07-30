import signal
from pathlib import Path

from app.core.config import load_config
from app.main import LuminaService, _ensure_directory, _run_startup_checks


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
  interval: 5
  log_level: INFO
storage:
  type: sqlite
  path: {tmp_path / "data" / "lumina.db"}
notify:
  wechat:
    enabled: false
""",
        encoding="utf-8",
    )
    stocks_path.write_text("stocks: []\n", encoding="utf-8")
    config = load_config(settings_path, stocks_path)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    _run_startup_checks(config, settings_path, stocks_path, log_dir)

    assert config.storage.path.parent.is_dir()


def test_graceful_exit_is_idempotent(tmp_path: Path) -> None:
    settings_path = Path("config/settings.yaml")
    stocks_path = Path("config/stocks.yaml")
    config = load_config(settings_path, stocks_path)
    service = LuminaService(config)

    service._handle_signal(signal.SIGTERM, None)
    service._handle_signal(signal.SIGTERM, None)

    assert service._stopping is True
