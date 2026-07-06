"""Performance and tail metrics over equity curves and trade lists.

Metrics are analytics, not money-path accounting: floats are fine here. The
tail block (ES95, worst trade, worst day, max losing cluster) exists because
§3 forbids accepting any change that degrades it, whatever Sharpe does.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise

_MIN_CURVE_LEN = 3
_MIN_RETURNS = 2


@dataclass(frozen=True)
class Metrics:
    n_bars: int
    n_trades: int
    total_return_pct: float
    sharpe: float
    max_drawdown_pct: float
    win_rate: float
    mean_trade_cents: float
    es95_cents: float
    worst_trade_cents: float
    worst_day_cents: float
    max_losing_cluster: int

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


def sharpe_ratio(equity_cents: list[int], bars_per_year: float) -> float:
    """Annualized Sharpe of per-bar simple returns on the equity curve."""
    if len(equity_cents) < _MIN_CURVE_LEN or bars_per_year <= 0:
        return 0.0
    returns = [(b - a) / a for a, b in pairwise(equity_cents) if a > 0]
    if len(returns) < _MIN_RETURNS:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if var == 0.0:
        return 0.0
    return mean / math.sqrt(var) * math.sqrt(bars_per_year)


def max_drawdown_pct(equity_cents: list[int]) -> float:
    peak = -1
    worst = 0.0
    for value in equity_cents:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return worst * 100.0


def es95_cents(trades: list[int]) -> float:
    """Expected shortfall: mean of the worst 5% of trades (at least one)."""
    if not trades:
        return 0.0
    ordered = sorted(trades)
    tail = ordered[: max(1, len(ordered) // 20)]
    return sum(tail) / len(tail)


def max_losing_cluster(trades: list[int]) -> int:
    longest = current = 0
    for trade in trades:
        current = current + 1 if trade < 0 else 0
        longest = max(longest, current)
    return longest


def compute_metrics(
    equity_curve: list[tuple[datetime, int]],
    trades: list[int],
    bars_per_year: float,
) -> Metrics:
    equity = [e for _, e in equity_curve]
    initial = equity[0] if equity else 0
    final = equity[-1] if equity else 0
    day_moves = [b - a for a, b in pairwise(equity)]
    wins = sum(1 for t in trades if t > 0)
    return Metrics(
        n_bars=len(equity),
        n_trades=len(trades),
        total_return_pct=((final - initial) / initial * 100.0) if initial else 0.0,
        sharpe=sharpe_ratio(equity, bars_per_year),
        max_drawdown_pct=max_drawdown_pct(equity),
        win_rate=(wins / len(trades)) if trades else 0.0,
        mean_trade_cents=(sum(trades) / len(trades)) if trades else 0.0,
        es95_cents=es95_cents(trades),
        worst_trade_cents=float(min(trades)) if trades else 0.0,
        worst_day_cents=float(min(day_moves)) if day_moves else 0.0,
        max_losing_cluster=max_losing_cluster(trades),
    )
