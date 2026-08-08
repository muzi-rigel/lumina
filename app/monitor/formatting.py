"""告警百分比的统一展示策略。"""

from decimal import Decimal

PERCENT_DISPLAY_PLACES = 4


def format_percent(value: Decimal) -> str:
    """仅在展示边界格式化四位小数，不影响内部 Decimal 比较精度。"""

    return f"{value:.{PERCENT_DISPLAY_PLACES}f}"
