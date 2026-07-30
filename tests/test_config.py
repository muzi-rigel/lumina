from pathlib import Path

import pytest

from app.core.config import ConfigError, load_config


def test_load_config_reads_valid_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "lumina.yaml"
    config_path.write_text(
        """
scheduler:
  interval_seconds: 15
logging:
  level: DEBUG
  file: logs/lumina.log
storage:
  database: data/lumina.db
  busy_timeout_seconds: 5
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.scheduler.interval_seconds == 15
    assert config.logging.level == "DEBUG"
    assert config.logging.file_path == Path("logs/lumina.log")
    assert config.storage.database_path == Path("data/lumina.db")


def test_load_config_rejects_invalid_interval(tmp_path: Path) -> None:
    config_path = tmp_path / "lumina.yaml"
    config_path.write_text(
        "scheduler:\n  interval_seconds: 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="必须大于 0"):
        load_config(config_path)


def test_load_config_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="配置文件不存在"):
        load_config(tmp_path / "missing.yaml")
