"""KA-3 (§4, G2 gate): MR governor grid on a synthetic P = F + u world.

F is a random walk with occasional jump-drift crash regimes; u is AR(1) mean
reversion. S2 runs across the 2x2x2 governor grid {trend filter, hard stop,
time stop}. Assertions per the plan:

- governors are approximately mean-neutral (they don't manufacture edge),
- but materially improve the left tail (ES95, worst trade, worst day),
- and with u == 0 (no mean reversion to harvest) any measured edge = bug.
"""

import random
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise, product
from pathlib import Path

import pytest
from tests.known_answer.helpers import T0, align, mean_stderr, round_trips
from tests.known_answer.strategies import S2KaStrategy

from qt.backtest.engine import Engine, EngineConfig
from qt.backtest.events import Bar
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel

CASH = 100_000_000
TICK = 0.10
TICK_VALUE_CENTS = 50
SEEDS = [3, 17, 29]
N_BARS = 2500
SMA_PERIOD = 100  # shorter warmup than production 200; same rule shape


def mr_world_bars(seed: int, n: int, mean_reversion: bool) -> list[Bar]:
    """P = F + u: F random walk with crash regimes, u AR(1) (or zero)."""
    rng = random.Random(seed)
    f = 2000.0
    u = 0.0
    crash_left = 0
    bars: list[Bar] = []
    prev_close = align(f, TICK)
    for i in range(n):
        if crash_left == 0 and rng.random() < 0.015:
            crash_left = 15  # jump-drift crash regime
        drift = -8.0 if crash_left > 0 else 0.0
        if crash_left > 0:
            crash_left -= 1
        f = max(f + drift + rng.gauss(0.0, 6.0), 300.0)
        u = 0.9 * u + rng.gauss(0.0, 3.0) if mean_reversion else 0.0
        close = align(max(f + u, 200.0), TICK)
        opn = prev_close
        high = max(opn, close) + TICK * rng.randint(0, 20)
        low = min(opn, close) - TICK * rng.randint(0, 20)
        bars.append(
            Bar(
                ts=T0 + timedelta(days=i),
                open=opn,
                high=high,
                low=max(low, 100.0),
                close=close,
                volume=1000.0,
            )
        )
        prev_close = close
    return bars


@dataclass(frozen=True)
class GridMetrics:
    n_trades: int
    mean: float
    stderr: float
    es95: float  # mean of the worst 5% of trades (cents)
    worst_trade: float
    worst_day: float  # worst single-bar equity change (cents)


def run_config(
    costs: CostModel, trend_filter: bool, hard_stop: bool, time_stop: bool
) -> GridMetrics:
    trades: list[int] = []
    worst_day = 0.0
    for seed in SEEDS:
        bars = mr_world_bars(seed, N_BARS, mean_reversion=True)
        strategy = S2KaStrategy(
            symbol="M2K",
            trend_filter=trend_filter,
            hard_stop=hard_stop,
            time_stop=time_stop,
            sma_period=SMA_PERIOD,
            tick=TICK,
        )
        result = Engine({"M2K": bars}, strategy, costs, EngineConfig(CASH)).run()
        trades.extend(round_trips(result.fills, tick=TICK, tick_value_cents=TICK_VALUE_CENTS))
        equities = [e for _, e in result.equity_curve]
        worst_day = min(worst_day, *(b - a for a, b in pairwise(equities)))
    assert trades, "grid cell produced no trades"
    ordered = sorted(trades)
    tail = ordered[: max(1, len(ordered) // 20)]
    mean, stderr = mean_stderr(trades)
    return GridMetrics(
        n_trades=len(trades),
        mean=mean,
        stderr=stderr,
        es95=sum(tail) / len(tail),
        worst_trade=ordered[0],
        worst_day=worst_day,
    )


@pytest.fixture(scope="module")
def grid(config_dir: Path) -> dict[tuple[bool, bool, bool], GridMetrics]:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    return {
        (tf, hs, ts): run_config(costs, tf, hs, ts)
        for tf, hs, ts in product([False, True], repeat=3)
    }


def test_ka3_grid_has_trades_everywhere(
    grid: dict[tuple[bool, bool, bool], GridMetrics],
) -> None:
    for key, metrics in grid.items():
        assert metrics.n_trades >= 30, f"{key}: only {metrics.n_trades} trades"


def test_ka3_governors_improve_left_tail(
    grid: dict[tuple[bool, bool, bool], GridMetrics],
) -> None:
    """All governors on vs all off: ES95, worst trade, and worst day must all
    improve materially (less negative)."""
    off = grid[False, False, False]
    on = grid[True, True, True]
    assert on.es95 > off.es95, f"ES95 not improved: on {on.es95:.0f} vs off {off.es95:.0f}"
    assert on.worst_trade > off.worst_trade, (
        f"worst trade not improved: on {on.worst_trade:.0f} vs off {off.worst_trade:.0f}"
    )
    assert on.worst_day >= off.worst_day, (
        f"worst day not improved: on {on.worst_day:.0f} vs off {off.worst_day:.0f}"
    )


def test_ka3_hard_stop_caps_worst_trade(
    grid: dict[tuple[bool, bool, bool], GridMetrics],
) -> None:
    """The hard stop specifically must truncate the worst trade, holding the
    other governors fixed."""
    for tf, ts in product([False, True], repeat=2):
        with_stop = grid[tf, True, ts]
        without = grid[tf, False, ts]
        assert with_stop.worst_trade > without.worst_trade, (
            f"hard stop did not cap worst trade at tf={tf}, ts={ts}"
        )


def test_ka3_governors_approximately_mean_neutral(
    grid: dict[tuple[bool, bool, bool], GridMetrics],
) -> None:
    """Governors reshape the tail, they don't manufacture expectancy: the
    all-on vs all-off mean gap must be small relative to the combined noise."""
    off = grid[False, False, False]
    on = grid[True, True, True]
    combined_stderr = (on.stderr**2 + off.stderr**2) ** 0.5
    assert abs(on.mean - off.mean) <= 3.0 * combined_stderr, (
        f"governors moved the mean: on {on.mean:.0f} vs off {off.mean:.0f} "
        f"(combined stderr {combined_stderr:.0f})"
    )


def test_ka3_no_edge_when_u_is_zero(config_dir: Path) -> None:
    """With u == 0 there is nothing to mean-revert; any measured S2 edge on the
    pure random-walk-with-crashes world is an engine bug."""
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    trades: list[int] = []
    for seed in SEEDS:
        bars = mr_world_bars(seed + 500, N_BARS, mean_reversion=False)
        strategy = S2KaStrategy(symbol="M2K", sma_period=SMA_PERIOD, tick=TICK)
        result = Engine({"M2K": bars}, strategy, costs, EngineConfig(CASH)).run()
        trades.extend(round_trips(result.fills, tick=TICK, tick_value_cents=TICK_VALUE_CENTS))
    assert len(trades) >= 20, f"too few trades ({len(trades)})"
    mean, stderr = mean_stderr(trades)
    assert mean <= 2 * stderr, f"S2 shows edge with u==0: mean {mean:.1f}c, stderr {stderr:.1f}c"
