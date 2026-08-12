import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import load_config
from app.core.scheduler import IntervalScheduler
from app.market.bootstrap import build_market_collector
from app.market.collector import MarketCollector
from app.market.source import QuoteBatch
from app.market.tencent_http import TencentHttpResult, UrllibTencentHttpTransport
from app.monitor.model import AlertEvent
from app.storage.database import SQLiteDatabase
from app.storage.repository import SQLiteMarketRepository

FIXTURE = Path("tests/fixtures/tencent_real_quotes.txt")


class RecordingNotifier:
    def __init__(self) -> None:
        self.alerts: list[AlertEvent] = []

    def send(self, alert: AlertEvent) -> None:
        self.alerts.append(alert)


def _write_config_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    settings_path = tmp_path / "settings.yaml"
    stocks_path = tmp_path / "stocks.yaml"
    rules_path = tmp_path / "rules.yaml"
    settings_path.write_text(
        f"""
app:
  name: lumina
  version: 0.1.0
  timezone: Asia/Shanghai
runtime:
  log_level: INFO
market:
  source: tencent
  interval_seconds: 0.01
  tencent:
    url: https://qt.gtimg.cn/q=
    timeout_seconds: 1
    batch_size: 50
    max_attempts: 1
    retry_backoff_seconds: 0
    max_total_seconds: 1
storage:
  type: sqlite
  path: {tmp_path / "lumina.db"}
notify:
  wechat:
    enabled: false
    webhook_env: LUMINA_WECHAT_URL
    timeout_seconds: 1
    max_attempts: 1
    retry_backoff_seconds: 0
    max_total_seconds: 1
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
    rules_path.write_text(
        """
rules:
  - id: tencent-day-rise
    name: 腾讯行情日内上涨
    type: DAY_CHANGE_PERCENT
    enabled: true
    direction: RISE
    threshold: "0.5"
    severity: WARNING
    cooldown_seconds: 0
    targets:
      codes:
        - "510300"
""",
        encoding="utf-8",
    )
    return settings_path, stocks_path, rules_path


def _build_dependencies(
    tmp_path: Path,
) -> tuple[SQLiteDatabase, SQLiteMarketRepository, RecordingNotifier, MarketCollector]:
    settings_path, stocks_path, rules_path = _write_config_files(tmp_path)
    config = load_config(settings_path, stocks_path, rules_path)
    database = SQLiteDatabase(config.storage.path, config.storage.busy_timeout_seconds)
    database.initialize()
    repository = SQLiteMarketRepository(
        database,
        clock=lambda: datetime(2026, 8, 8, tzinfo=UTC),
    )
    notifier = RecordingNotifier()
    collector = build_market_collector(config, repository, notifier)
    return database, repository, notifier, collector


def test_tencent_quote_runs_through_existing_storage_rule_and_alert_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = FIXTURE.read_bytes().splitlines()[0]
    calls: list[tuple[str, float]] = []

    def fake_get(
        transport: UrllibTencentHttpTransport,
        url: str,
        timeout: float,
    ) -> TencentHttpResult:
        del transport
        calls.append((url, timeout))
        return TencentHttpResult(200, body)

    monkeypatch.setattr(UrllibTencentHttpTransport, "get", fake_get)
    database, _repository, notifier, collector = _build_dependencies(tmp_path)

    with caplog.at_level(logging.INFO):
        batch = collector.collect_once()

    assert batch is not None
    assert batch.source == "tencent"
    assert len(batch.quotes) == 1
    assert calls[0][0].endswith("q=sh510300")
    assert batch.quotes[0].timestamp.isoformat() == "2026-08-07T16:14:52+08:00"
    assert len(notifier.alerts) == 1
    assert notifier.alerts[0].rule_id == "tencent-day-rise"
    assert notifier.alerts[0].current_price == batch.quotes[0].price

    with database.session() as connection:
        quote_row = connection.execute(
            """SELECT code, name, instrument_type, price, volume, quote_time
            FROM quote_snapshot"""
        ).fetchone()
        alert_row = connection.execute("SELECT code, rule_id, severity FROM alert_event").fetchone()
    assert quote_row == (
        "510300",
        "沪深300ETF",
        "ETF",
        "4.751",
        9_435_356,
        "2026-08-07T08:14:52.000000+00:00",
    )
    assert alert_row == ("510300", "tencent-day-rise", "WARNING")
    assert "alert rule_id=tencent-day-rise code=510300" in caplog.text


def test_tencent_source_error_ends_only_current_scheduler_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = FIXTURE.read_bytes().splitlines()[0]
    outcomes: list[Exception | TencentHttpResult] = [
        TimeoutError("temporary timeout"),
        TencentHttpResult(200, body),
    ]

    def fake_get(
        transport: UrllibTencentHttpTransport,
        url: str,
        timeout: float,
    ) -> TencentHttpResult:
        del transport, url, timeout
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(UrllibTencentHttpTransport, "get", fake_get)
    _database, _repository, _notifier, collector = _build_dependencies(tmp_path)
    scheduler = IntervalScheduler(interval_seconds=0.01)
    results: list[QuoteBatch | None] = []

    def collect() -> None:
        results.append(collector.collect_once())
        if len(results) == 2:
            scheduler.stop()

    scheduler.add_task("market-collection", collect)
    with caplog.at_level(logging.ERROR, logger="app.market.collector"):
        scheduler.run()

    assert results[0] is None
    assert results[1] is not None
    assert len(results[1].quotes) == 1
    assert "行情源故障 source=tencent error_type=MarketSourceError" in caplog.text
