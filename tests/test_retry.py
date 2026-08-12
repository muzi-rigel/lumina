import math

import pytest

from app.core.retry import RetryBudgetExceeded, RetryController, RetryPolicy


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_retry_controller_exposes_attempts_and_exponential_backoff() -> None:
    clock = FakeTime()
    controller = RetryController(
        RetryPolicy(max_attempts=3, backoff_seconds=1, max_total_seconds=10),
        timeout_seconds=4,
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    )

    attempts = list(controller)

    assert [attempt.number for attempt in attempts] == [1, 2, 3]
    assert [attempt.timeout_seconds for attempt in attempts] == [4, 4, 4]
    assert clock.sleeps == [1, 2]


def test_retry_controller_caps_timeout_by_remaining_budget() -> None:
    clock = FakeTime()
    controller = RetryController(
        RetryPolicy(max_attempts=1, backoff_seconds=0, max_total_seconds=2),
        timeout_seconds=5,
        monotonic=clock.monotonic,
    )

    assert next(iter(controller)).timeout_seconds == 2


def test_retry_controller_rejects_backoff_beyond_budget() -> None:
    clock = FakeTime()
    controller = RetryController(
        RetryPolicy(max_attempts=2, backoff_seconds=5, max_total_seconds=2),
        timeout_seconds=1,
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    )

    with pytest.raises(RetryBudgetExceeded):
        list(controller)

    assert clock.sleeps == []


def test_retry_controller_does_not_swallow_caller_exception() -> None:
    class ExpectedError(RuntimeError):
        pass

    clock = FakeTime()
    controller = RetryController(
        RetryPolicy(max_attempts=3, backoff_seconds=1, max_total_seconds=10),
        timeout_seconds=2,
        sleeper=clock.sleep,
        monotonic=clock.monotonic,
    )

    with pytest.raises(ExpectedError, match="调用失败"):
        for _attempt in controller:
            raise ExpectedError("调用失败")

    assert clock.sleeps == []


@pytest.mark.parametrize(
    "policy",
    [
        RetryPolicy(max_attempts=1, backoff_seconds=0, max_total_seconds=1),
    ],
)
@pytest.mark.parametrize("timeout", [0, -1, math.inf, math.nan])
def test_retry_controller_rejects_invalid_timeout(
    policy: RetryPolicy,
    timeout: float,
) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        RetryController(policy, timeout)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0, "backoff_seconds": 0, "max_total_seconds": 1},
        {"max_attempts": -1, "backoff_seconds": 0, "max_total_seconds": 1},
        {"max_attempts": True, "backoff_seconds": 0, "max_total_seconds": 1},
        {"max_attempts": 1, "backoff_seconds": -1, "max_total_seconds": 1},
        {"max_attempts": 1, "backoff_seconds": 0, "max_total_seconds": 0},
    ],
)
def test_retry_policy_rejects_invalid_bounds(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)
