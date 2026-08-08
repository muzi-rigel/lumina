"""根据规则配置构建内存监控引擎。"""

from __future__ import annotations

import math
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from app.monitor.engine import MonitorEngine
from app.monitor.history import QuoteHistory
from app.monitor.model import RuleDefinition
from app.monitor.rules import create_rule
from app.monitor.state import AlertStateStore


def build_monitor_engine(
    definitions: Iterable[RuleDefinition],
    interval_seconds: float,
    timezone_name: str,
) -> MonitorEngine:
    """按最大启用窗口计算历史保留期和异常保护容量。"""

    enabled = tuple(definition for definition in definitions if definition.enabled)
    rules = tuple(create_rule(definition) for definition in enabled)
    max_window = max((definition.window_seconds or 0 for definition in enabled), default=0)
    safety_seconds = max(60, math.ceil(interval_seconds * 2))
    retention_seconds = max_window + safety_seconds
    expected_points = math.ceil(retention_seconds / interval_seconds)
    max_points = max(3, expected_points + 2)

    history = QuoteHistory(
        retention_seconds=retention_seconds,
        max_points_per_symbol=max_points,
        timezone=ZoneInfo(timezone_name),
    )
    return MonitorEngine(
        rules=rules,
        history=history,
        state_store=AlertStateStore(),
    )
