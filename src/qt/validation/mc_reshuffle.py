"""Monte Carlo trade-order reshuffle (§3 validation battery).

Trade P&Ls are exchangeable under the null that their order carries no
information; reshuffling the order maps out the drawdown distribution the
SAME trades could have produced. 10k paths is the plan's default.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

_MIN_TRADES = 2


@dataclass(frozen=True)
class ReshuffleResult:
    n_paths: int
    observed_max_drawdown_cents: int
    drawdown_p05_cents: float  # 5th percentile (mild outcomes)
    drawdown_p50_cents: float
    drawdown_p95_cents: float  # deep tail
    drawdown_worst_cents: int
    observed_percentile: float  # where the observed drawdown sits in [0, 1]


def max_drawdown_cents(trades: list[int]) -> int:
    peak = equity = 0
    worst = 0
    for trade in trades:
        equity += trade
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _percentile(ordered: list[int], pct: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    rank = pct / 100.0 * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def reshuffle_drawdowns(trades: list[int], n_paths: int = 10_000, seed: int = 7) -> ReshuffleResult:
    if len(trades) < _MIN_TRADES:
        msg = f"reshuffle needs at least 2 trades, got {len(trades)}"
        raise ValueError(msg)
    rng = random.Random(seed)
    observed = max_drawdown_cents(trades)
    drawdowns: list[int] = []
    shuffled = list(trades)
    for _ in range(n_paths):
        rng.shuffle(shuffled)
        drawdowns.append(max_drawdown_cents(shuffled))
    drawdowns.sort()  # ascending: most negative (deepest) first
    at_or_deeper = sum(1 for d in drawdowns if d <= observed)
    return ReshuffleResult(
        n_paths=n_paths,
        observed_max_drawdown_cents=observed,
        drawdown_p05_cents=_percentile(drawdowns, 95.0),  # shallow end
        drawdown_p50_cents=_percentile(drawdowns, 50.0),
        drawdown_p95_cents=_percentile(drawdowns, 5.0),  # deep end
        drawdown_worst_cents=drawdowns[0],
        observed_percentile=at_or_deeper / n_paths,
    )
