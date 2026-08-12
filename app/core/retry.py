"""与业务和传输协议无关的同步重试预算。"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass


class RetryBudgetExceeded(RuntimeError):
    """重试过程已没有足够的总耗时预算。"""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: float
    max_total_seconds: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attempts 必须是大于 0 的整数")
        if not math.isfinite(self.backoff_seconds) or self.backoff_seconds < 0:
            raise ValueError("backoff_seconds 必须是非负有限数值")
        if not math.isfinite(self.max_total_seconds) or self.max_total_seconds <= 0:
            raise ValueError("max_total_seconds 必须是大于 0 的有限数值")


@dataclass(frozen=True, slots=True)
class RetryAttempt:
    number: int
    timeout_seconds: float


class RetryController:
    """调用方继续迭代即表示需要重试，本类不判断具体错误。"""

    def __init__(
        self,
        policy: RetryPolicy,
        timeout_seconds: float,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须是大于 0 的有限数值")
        self._policy = policy
        self._timeout = timeout_seconds
        self._sleeper = sleeper
        self._monotonic = monotonic

    def __iter__(self) -> Iterator[RetryAttempt]:
        started_at = self._monotonic()
        for number in range(1, self._policy.max_attempts + 1):
            remaining = self._remaining(started_at)
            if remaining <= 0:
                raise RetryBudgetExceeded("重试已超过最大总耗时")
            yield RetryAttempt(number, min(self._timeout, remaining))

            if number == self._policy.max_attempts:
                return
            delay = self._policy.backoff_seconds * (2 ** (number - 1))
            remaining = self._remaining(started_at)
            if delay >= remaining:
                raise RetryBudgetExceeded("剩余预算不足以执行下一次退避")
            if delay > 0:
                self._sleeper(delay)

    def _remaining(self, started_at: float) -> float:
        elapsed = self._monotonic() - started_at
        return self._policy.max_total_seconds - elapsed
