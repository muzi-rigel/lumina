import json
from datetime import datetime
from decimal import Decimal
from typing import Self, cast
from urllib.request import Request
from zoneinfo import ZoneInfo

import pytest

from app.market.model import InstrumentType
from app.monitor.model import (
    AlertEvent,
    AlertSeverity,
    RuleDirection,
    RuleType,
)
from app.notify.formatter import MessageFormat, MessagePayload
from app.notify.wechat import (
    HttpResult,
    NotificationError,
    UrllibHttpTransport,
    WeChatNotifier,
)


class StubFormatter:
    def format(self, alert: AlertEvent) -> MessagePayload:
        del alert
        return MessagePayload(MessageFormat.MARKDOWN, "测试消息")


class ScriptedTransport:
    def __init__(self, outcomes: list[HttpResult | Exception]) -> None:
        self._outcomes = outcomes
        self.calls: list[tuple[str, dict[str, object], float]] = []

    def post_json(self, url: str, payload: dict[str, object], timeout: float) -> HttpResult:
        self.calls.append((url, payload, timeout))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _alert() -> AlertEvent:
    timestamp = datetime(2026, 8, 8, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    return AlertEvent(
        code="510300",
        name="沪深300ETF",
        instrument_type=InstrumentType.ETF,
        rule_id="day-rise",
        rule_name="日内上涨",
        rule_type=RuleType.DAY_CHANGE_PERCENT,
        direction=RuleDirection.RISE,
        severity=AlertSeverity.WARNING,
        triggered_at=timestamp,
        current_price=Decimal("4.1"),
        actual_change_percent=Decimal("2.5"),
        threshold=Decimal("2"),
        window_seconds=None,
        reference_price=Decimal("4"),
        reference_time=None,
        message="测试",
    )


def _success() -> HttpResult:
    return HttpResult(200, b'{"errcode":0,"errmsg":"ok"}')


def _notifier(
    outcomes: list[HttpResult | Exception],
    *,
    fake_time: FakeTime | None = None,
    timeout: float = 5,
    attempts: int = 3,
    backoff: float = 1,
    max_total: float = 15,
) -> tuple[WeChatNotifier, ScriptedTransport, FakeTime]:
    clock = fake_time or FakeTime()
    transport = ScriptedTransport(outcomes)
    notifier = WeChatNotifier(
        webhook_url="https://example.test/webhook?key=secret",
        formatter=StubFormatter(),
        timeout_seconds=timeout,
        max_attempts=attempts,
        retry_backoff_seconds=backoff,
        max_total_seconds=max_total,
        transport=transport,
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    )
    return notifier, transport, clock


def test_success_sends_expected_wechat_payload() -> None:
    notifier, transport, _ = _notifier([_success()])

    notifier.send(_alert())

    assert len(transport.calls) == 1
    assert transport.calls[0][1] == {
        "msgtype": "markdown",
        "markdown": {"content": "测试消息"},
    }


def test_standard_library_transport_posts_utf8_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def getcode(self) -> int:
            return 200

        def read(self, amount: int) -> bytes:
            captured["read_amount"] = amount
            return b'{"errcode":0}'

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.notify.wechat.urlopen", fake_urlopen)
    result = UrllibHttpTransport().post_json(
        "https://example.test/webhook?key=secret",
        {"msgtype": "text", "text": {"content": "中文"}},
        timeout=2,
    )

    request = cast(Request, captured["request"])
    assert result.status_code == 200
    assert captured["timeout"] == 2
    assert request.data is not None
    assert json.loads(request.data.decode("utf-8")) == {
        "msgtype": "text",
        "text": {"content": "中文"},
    }
    assert request.get_header("Content-type") == "application/json; charset=utf-8"


@pytest.mark.parametrize(
    "first_outcome",
    [
        HttpResult(429, b""),
        HttpResult(503, b""),
        HttpResult(200, b'{"errcode":45009,"errmsg":"rate limit"}'),
        TimeoutError("timeout"),
    ],
)
def test_retryable_failures_use_bounded_backoff(first_outcome: HttpResult | Exception) -> None:
    notifier, transport, clock = _notifier([first_outcome, _success()])

    notifier.send(_alert())

    assert len(transport.calls) == 2
    assert clock.sleeps == [1]


def test_permanent_http_error_is_not_retried() -> None:
    notifier, transport, _ = _notifier([HttpResult(400, b"bad request")])

    with pytest.raises(NotificationError, match="400"):
        notifier.send(_alert())

    assert len(transport.calls) == 1


def test_invalid_json_retries_only_to_attempt_limit() -> None:
    notifier, transport, clock = _notifier(
        [HttpResult(200, b"invalid"), HttpResult(200, b"invalid")],
        attempts=2,
    )

    with pytest.raises(NotificationError, match="有效 JSON"):
        notifier.send(_alert())

    assert len(transport.calls) == 2
    assert clock.sleeps == [1]


def test_max_total_budget_caps_timeout_and_prevents_long_backoff() -> None:
    notifier, transport, clock = _notifier(
        [HttpResult(503, b"")],
        timeout=10,
        backoff=5,
        max_total=2,
    )

    with pytest.raises(NotificationError, match="最大总耗时"):
        notifier.send(_alert())

    assert transport.calls[0][2] == 2
    assert clock.sleeps == []


def test_error_never_contains_webhook_secret() -> None:
    notifier, _, _ = _notifier([HttpResult(400, b"")])

    with pytest.raises(NotificationError) as error:
        notifier.send(_alert())

    assert "secret" not in str(error.value)
