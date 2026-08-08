"""监控规则定义、评估结果和标准化告警事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.market.model import InstrumentType, MarketInstrument


class RuleType(StrEnum):
    DAY_CHANGE_PERCENT = "DAY_CHANGE_PERCENT"
    WINDOW_CHANGE_PERCENT = "WINDOW_CHANGE_PERCENT"


class RuleDirection(StrEnum):
    RISE = "RISE"
    FALL = "FALL"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class MatchStatus(StrEnum):
    """规则指标相对条件的三态结果。"""

    MATCHED = "MATCHED"
    NOT_MATCHED = "NOT_MATCHED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RuleTargets:
    """规则目标；代码和类型在配置层保证互斥。"""

    codes: frozenset[str] = field(default_factory=frozenset)
    instrument_types: frozenset[InstrumentType] = field(default_factory=frozenset)

    def applies_to(self, instrument: MarketInstrument) -> bool:
        if self.codes:
            return instrument.code in self.codes
        if self.instrument_types:
            return instrument.type in self.instrument_types
        return True


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    id: str
    name: str
    type: RuleType
    enabled: bool
    direction: RuleDirection
    threshold: Decimal
    severity: AlertSeverity
    cooldown_seconds: int
    window_seconds: int | None
    targets: RuleTargets

    @property
    def effective_threshold(self) -> Decimal:
        """返回用于比较和展示的带方向阈值。"""

        if self.direction is RuleDirection.RISE:
            return self.threshold
        return -self.threshold


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """规则指标计算结果；UNKNOWN 不携带实际涨跌幅。"""

    status: MatchStatus
    actual_change_percent: Decimal | None
    reference_price: Decimal | None
    reference_time: datetime | None


@dataclass(frozen=True, slots=True)
class AlertEvent:
    """与通知渠道和存储方式无关的标准化告警事件。"""

    code: str
    name: str
    instrument_type: InstrumentType
    rule_id: str
    rule_name: str
    rule_type: RuleType
    direction: RuleDirection
    severity: AlertSeverity
    triggered_at: datetime
    current_price: Decimal
    actual_change_percent: Decimal
    threshold: Decimal
    window_seconds: int | None
    reference_price: Decimal
    reference_time: datetime | None
    message: str
