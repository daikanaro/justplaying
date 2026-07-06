"""KA-1 (§4, G2 gate): no edge on GBM, and the first-passage signature.

(a) S1 and S2 logic on driftless GBM must show net-of-cost expectancy <= 0
    within confidence bounds — GBM has no autocorrelation, so ANY significant
    positive edge is an engine bug (lookahead, fill bias, accounting).
(b) First-passage signature on a symmetric +/-1-tick walk with barriers a
    ticks below and b above: P(hit up first) = a/(a+b) and payoff = b/a.
    Exercises the stop-trigger mechanics against exact theory.
"""

import random
from datetime import timedelta
from pathlib import Path

import pytest
from tests.known_answer.helpers import T0, gbm_bars, mean_stderr, round_trips
from tests.known_answer.strategies import S1KaStrategy, S2KaStrategy

from qt.backtest.engine import Engine, EngineConfig
from qt.backtest.events import Bar
from qt.backtest.execution import ExecutionSimulator
from qt.backtest.orders import Side, StopOrder
from qt.config import InstrumentsConfig, load_config
from qt.config.schemas import InstrumentSpec, SlippageConfig
from qt.costs.model import CostModel

CASH = 100_000_000  # $1M so margin never interferes with the statistics
SEEDS = [11, 23, 47, 91]


@pytest.fixture(scope="module")
def costs(config_dir: Path) -> CostModel:
    return CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))


def test_ka1_s1_no_edge_on_gbm(costs: CostModel) -> None:
    trades: list[int] = []
    for seed in SEEDS:
        bars = gbm_bars(seed, 2500, tick=0.25)
        strategy = S1KaStrategy(symbol="MES", donchian_n=20, atr_k=3.0, atr_period=20)
        result = Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()
        trades.extend(round_trips(result.fills, tick=0.25, tick_value_cents=125))
    assert len(trades) >= 40, f"too few trades ({len(trades)}) for a meaningful KA-1"
    mean, stderr = mean_stderr(trades)
    # Expectancy must not be significantly positive; with costs it should sit at or
    # below zero. Any breach here = engine bug, investigate before proceeding.
    assert mean <= 2 * stderr, f"S1 shows edge on GBM: mean {mean:.1f}c, stderr {stderr:.1f}c"


def test_ka1_s2_no_edge_on_gbm(costs: CostModel) -> None:
    trades: list[int] = []
    for seed in SEEDS:
        bars = gbm_bars(seed + 1000, 2500, s0=2000.0, sigma_per_bar=0.012, tick=0.10, bar_hours=24)
        strategy = S2KaStrategy(symbol="M2K", sma_period=100)  # shorter warmup, same rules
        result = Engine({"M2K": bars}, strategy, costs, EngineConfig(CASH)).run()
        trades.extend(round_trips(result.fills, tick=0.10, tick_value_cents=50))
    assert len(trades) >= 40, f"too few trades ({len(trades)}) for a meaningful KA-1"
    mean, stderr = mean_stderr(trades)
    assert mean <= 2 * stderr, f"S2 shows edge on GBM: mean {mean:.1f}c, stderr {stderr:.1f}c"


# ---------------------------------------------------------------------------
# First-passage signature
# ---------------------------------------------------------------------------


def _frictionless_costs() -> CostModel:
    """Zero commission/slippage so fills sit exactly on the barriers."""
    config = InstrumentsConfig(
        instruments={
            "MES": InstrumentSpec(
                name="Micro E-mini S&P 500",
                exchange="CME",
                currency="USD",
                dollars_per_point=5.0,
                tick_size=0.25,
                tick_value=1.25,
                commission_per_side=0.0,
                maintenance_margin=2400.0,
            )
        },
        slippage=SlippageConfig(
            rth_ticks_per_side=0, eth_ticks_per_side=0, stress_multipliers=[1, 2, 3]
        ),
    )
    return CostModel(config)


def _tick_walk_bar(index: int, prev: float, nxt: float) -> Bar:
    return Bar(
        ts=T0 + timedelta(hours=index),
        open=prev,
        high=max(prev, nxt),
        low=min(prev, nxt),
        close=nxt,
        volume=1.0,
    )


def test_ka1_first_passage_signature() -> None:
    tick = 0.25
    a, b = 3, 5  # barriers: a ticks below entry, b ticks above
    p0 = 5000.0
    n_walks = 1500
    sim = ExecutionSimulator(_frictionless_costs())
    rng = random.Random(7)

    ups = 0
    up_gain_ticks: list[float] = []
    down_loss_ticks: list[float] = []
    for _ in range(n_walks):
        lower = StopOrder(symbol="MES", side=Side.SELL, quantity=1, stop_price=p0 - a * tick)
        upper = StopOrder(symbol="MES", side=Side.BUY, quantity=1, stop_price=p0 + b * tick)
        price = p0
        index = 0
        while True:
            nxt = price + tick * (1 if rng.random() < 0.5 else -1)
            bar = _tick_walk_bar(index, price, nxt)
            down = sim.try_fill_stop(lower, bar, "down")
            up = sim.try_fill_stop(upper, bar, "up")
            if down is not None:
                # A 1-tick walk cannot gap: the fill must sit exactly on the barrier.
                assert down.price == pytest.approx(p0 - a * tick)
                down_loss_ticks.append((p0 - down.price) / tick)
                break
            if up is not None:
                assert up.price == pytest.approx(p0 + b * tick)
                ups += 1
                up_gain_ticks.append((up.price - p0) / tick)
                break
            price = nxt
            index += 1

    hit_rate = ups / n_walks
    theoretical = a / (a + b)  # 0.375
    assert hit_rate == pytest.approx(theoretical, abs=0.04), (
        f"first-passage hit rate {hit_rate:.3f} != {theoretical:.3f}"
    )
    payoff = (sum(up_gain_ticks) / len(up_gain_ticks)) / (
        sum(down_loss_ticks) / len(down_loss_ticks)
    )
    assert payoff == pytest.approx(b / a, rel=1e-9), "payoff ratio must be exactly b/a"
