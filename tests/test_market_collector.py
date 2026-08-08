import logging

import pytest

from app.market.collector import MarketCollector
from app.market.model import MarketQuote
from app.market.source import QuoteFailure
from tests.collector_fakes import (
    FlakySource,
    RecordingMonitorEngine,
    RecordingNotifier,
    RecordingRepository,
    StubSource,
    alert,
    batch,
    instrument,
    quote,
)


def test_collector_processes_normal_batch_with_unified_quote(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = instrument("510300", "沪深300ETF")
    market_quote = quote(value)
    engine = RecordingMonitorEngine()
    repository = RecordingRepository()
    collector = MarketCollector(
        StubSource(batch((market_quote,))),
        [value],
        engine,
        repository,
        RecordingNotifier(),
    )

    with caplog.at_level(logging.INFO, logger="app.market.collector"):
        result = collector.collect_once()

    assert result is not None
    assert engine.received == [market_quote]
    assert isinstance(engine.received[0], MarketQuote)
    assert repository.quotes == [market_quote]
    assert "行情成功 code=510300 name=沪深300ETF" in caplog.text
    assert "price=4.050 change=0.050 change_pct=1.2500%" in caplog.text


def test_partial_failure_does_not_drop_success(caplog: pytest.LogCaptureFixture) -> None:
    success = instrument("510300", "沪深300ETF")
    failed = instrument("512480", "半导体ETF")
    market_quote = quote(success)
    failure = QuoteFailure(failed, "模拟失败", retryable=True)
    engine = RecordingMonitorEngine()
    collector = MarketCollector(
        StubSource(batch((market_quote,), (failure,))),
        [success, failed],
        engine,
        RecordingRepository(),
        RecordingNotifier(),
    )

    with caplog.at_level(logging.WARNING, logger="app.market.collector"):
        collector.collect_once()

    assert engine.received == [market_quote]
    assert "行情失败 code=512480 reason=模拟失败" in caplog.text


def test_monitor_exception_isolated_per_quote(caplog: pytest.LogCaptureFixture) -> None:
    first = instrument("510300", "沪深300ETF")
    second = instrument("512480", "半导体ETF")
    engine = RecordingMonitorEngine(exploding_code=first.code)
    collector = MarketCollector(
        StubSource(batch((quote(first), quote(second)))),
        [first, second],
        engine,
        RecordingRepository(),
        RecordingNotifier(),
    )

    with caplog.at_level(logging.ERROR, logger="app.market.collector"):
        collector.collect_once()

    assert [item.symbol for item in engine.received] == [first.code, second.code]
    assert "行情处理异常 code=510300" in caplog.text
    assert "error_type=RuntimeError reason=模拟监控引擎异常" in caplog.text


def test_collector_logs_stores_and_notifies_alert(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = instrument("510300", "沪深300ETF")
    market_quote = quote(value)
    event = alert(market_quote)
    repository = RecordingRepository()
    notifier = RecordingNotifier()
    collector = MarketCollector(
        StubSource(batch((market_quote,))),
        [value],
        RecordingMonitorEngine(alerts=[event]),
        repository,
        notifier,
    )

    with caplog.at_level(logging.WARNING, logger="app.market.collector"):
        collector.collect_once()

    assert "alert rule_id=day-rise code=510300 name=沪深300ETF" in caplog.text
    assert "actual_change_pct=1.2500 threshold=1.0000" in caplog.text
    assert repository.alerts == [event]
    assert notifier.alerts == [event]


def test_quote_storage_failure_does_not_skip_rules_or_other_quotes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = instrument("510300", "沪深300ETF")
    second = instrument("512480", "半导体ETF")
    engine = RecordingMonitorEngine()
    repository = RecordingRepository(failing_quote_codes=frozenset({first.code}))
    collector = MarketCollector(
        StubSource(batch((quote(first), quote(second)))),
        [first, second],
        engine,
        repository,
        RecordingNotifier(),
    )

    with caplog.at_level(logging.ERROR, logger="app.market.collector"):
        collector.collect_once()

    assert [item.symbol for item in engine.received] == [first.code, second.code]
    assert repository.quotes == [quote(second)]
    assert "行情保存失败 code=510300 quote_time=" in caplog.text


def test_alert_storage_failure_still_logs_and_notifies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = instrument("510300", "沪深300ETF")
    market_quote = quote(value)
    first = alert(market_quote, "first")
    second = alert(market_quote, "second")
    repository = RecordingRepository(failing_rule_ids=frozenset({"first"}))
    notifier = RecordingNotifier()
    collector = MarketCollector(
        StubSource(batch((market_quote,))),
        [value],
        RecordingMonitorEngine(alerts=[first, second]),
        repository,
        notifier,
    )

    with caplog.at_level(logging.WARNING, logger="app.market.collector"):
        collector.collect_once()

    assert repository.alerts == [second]
    assert notifier.alerts == [first, second]
    messages = [record.getMessage() for record in caplog.records]
    alert_log = next(
        i for i, message in enumerate(messages) if message.startswith("alert rule_id=first")
    )
    error_log = next(i for i, message in enumerate(messages) if message.startswith("告警保存失败"))
    assert alert_log < error_log


def test_notification_failure_does_not_affect_later_alerts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = instrument("510300", "沪深300ETF")
    market_quote = quote(value)
    first = alert(market_quote, "first")
    second = alert(market_quote, "second")
    repository = RecordingRepository()
    notifier = RecordingNotifier(failing_rule_ids=frozenset({"first"}))
    collector = MarketCollector(
        StubSource(batch((market_quote,))),
        [value],
        RecordingMonitorEngine(alerts=[first, second]),
        repository,
        notifier,
    )

    with caplog.at_level(logging.WARNING, logger="app.market.collector"):
        collector.collect_once()

    assert repository.alerts == [first, second]
    assert notifier.alerts == [second]
    assert "告警通知失败 code=510300 rule_id=first" in caplog.text
    assert "error_type=RuntimeError reason=模拟通知故障" in caplog.text


def test_storage_rule_and_notification_processing_order() -> None:
    operations: list[str] = []
    value = instrument("510300", "沪深300ETF")
    market_quote = quote(value)
    collector = MarketCollector(
        StubSource(batch((market_quote,))),
        [value],
        RecordingMonitorEngine(alerts=[alert(market_quote)], operations=operations),
        RecordingRepository(operations=operations),
        RecordingNotifier(operations=operations),
    )

    collector.collect_once()

    assert operations == [
        "save_quote:510300",
        "evaluate:510300",
        "save_alert:day-rise",
        "send:day-rise",
    ]


def test_market_source_error_only_ends_current_cycle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = instrument("510300", "沪深300ETF")
    engine = RecordingMonitorEngine()
    source = FlakySource(batch((quote(value, source="flaky"),), source="flaky"))
    collector = MarketCollector(
        source,
        [value],
        engine,
        RecordingRepository(),
        RecordingNotifier(),
    )

    with caplog.at_level(logging.ERROR, logger="app.market.collector"):
        first_result = collector.collect_once()
        second_result = collector.collect_once()

    assert first_result is None
    assert second_result is not None
    assert engine.received == [quote(value, source="flaky")]
    assert "行情源故障 source=flaky" in caplog.text
