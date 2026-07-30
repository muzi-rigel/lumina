"""适合单进程长期运行服务的轻量周期调度器。"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledTask:
    """一个具名周期任务。"""

    name: str
    callback: Callable[[], None]


class IntervalScheduler:
    """串行执行周期任务，并隔离单个任务的异常。"""

    def __init__(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds 必须大于 0")
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._tasks: list[ScheduledTask] = []
        self._lock = threading.RLock()

    def add_task(self, name: str, callback: Callable[[], None]) -> None:
        if not name.strip():
            raise ValueError("任务名称不能为空")
        with self._lock:
            if any(task.name == name for task in self._tasks):
                raise ValueError(f"任务名称重复：{name}")
            self._tasks.append(ScheduledTask(name=name, callback=callback))

    def stop(self) -> None:
        """请求调度循环尽快停止。"""

        self._stop_event.set()

    def run(self) -> None:
        """运行调度循环，直到收到停止请求。"""

        logger.info("周期调度器已启动，间隔 %.1f 秒", self._interval_seconds)
        while not self._stop_event.is_set():
            cycle_started = time.monotonic()
            with self._lock:
                tasks = tuple(self._tasks)

            for task in tasks:
                if self._stop_event.is_set():
                    break
                try:
                    task.callback()
                except Exception:
                    logger.exception("周期任务执行失败，任务=%s", task.name)

            elapsed = time.monotonic() - cycle_started
            wait_seconds = max(0.0, self._interval_seconds - elapsed)
            self._stop_event.wait(wait_seconds)

        logger.info("周期调度器已停止")
