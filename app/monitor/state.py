"""告警边沿触发和冷却状态。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.monitor.model import MatchStatus


@dataclass(slots=True)
class _RuleState:
    matched: bool = False
    armed: bool = True
    last_triggered_at: datetime | None = None
    last_evaluated_at: datetime | None = None


class AlertStateStore:
    """按 (code, rule_id) 隔离状态，严格采用边沿触发。"""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], _RuleState] = {}

    def reset_code(self, code: str) -> None:
        """新自然日期开始时删除该代码的全部规则状态。"""

        keys = [key for key in self._states if key[0] == code]
        for key in keys:
            del self._states[key]

    def should_trigger(
        self,
        code: str,
        rule_id: str,
        status: MatchStatus,
        observed_at: datetime,
        cooldown_seconds: int,
    ) -> bool:
        """更新状态并返回当前行情是否产生告警。"""

        if status is MatchStatus.UNKNOWN:
            return False

        state = self._states.setdefault((code, rule_id), _RuleState())
        if state.last_evaluated_at is not None and observed_at < state.last_evaluated_at:
            return False
        state.last_evaluated_at = observed_at

        if status is MatchStatus.NOT_MATCHED:
            state.matched = False
            state.armed = True
            return False

        if state.matched:
            return False

        state.matched = True
        if not state.armed:
            return False
        # 无论是否处于冷却期，这次上升沿都会被消费，不做延迟补发。
        state.armed = False

        if state.last_triggered_at is None:
            state.last_triggered_at = observed_at
            return True
        if observed_at <= state.last_triggered_at:
            return False
        cooldown = timedelta(seconds=cooldown_seconds)
        if observed_at - state.last_triggered_at < cooldown:
            return False
        state.last_triggered_at = observed_at
        return True
