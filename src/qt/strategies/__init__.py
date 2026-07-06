"""Production strategies (BUILD_PLAN §3, slice 4.4).

Strategies implement ``on_bar(ctx) -> dict[symbol, target_contracts]`` and
never emit orders; protective stops go through the engine's never-widen API.
Sizing follows §1 exactly (see :mod:`qt.strategies.sizing`).
"""

from qt.strategies.s1_trend_breakout import S1TrendBreakout
from qt.strategies.s2_mr_rsi2 import S2MeanReversion
from qt.strategies.sizing import size_position

__all__ = ["S1TrendBreakout", "S2MeanReversion", "size_position"]
