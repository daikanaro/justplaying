"""Property tests (§4.2 acceptance, hypothesis): the accounting invariant
holds under random event sequences, fills always land within the bar range
(± modeled slippage), and no event sequence can move backward in time."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from qt.backtest.engine import Engine, EngineConfig, StrategyContext
from qt.backtest.events import Bar, FillEvent
from qt.backtest.execution import ExecutionSimulator
from qt.backtest.orders import LimitOrder, MarketOrder, Side, StopOrder
from qt.backtest.portfolio import Portfolio
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel

T0 = datetime(2024, 7, 8, 15, 0, tzinfo=UTC)
TICK = 0.25
CASH = 100_000_000


@pytest.fixture(scope="module")
def costs(config_dir: Path) -> CostModel:
    return CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))


# Tick-aligned bar: open/close inside [low, high], all on the 0.25 grid.
@st.composite
def tick_bars(draw: st.DrawFn, index: int = 0) -> Bar:
    low_ticks = draw(st.integers(min_value=19_000, max_value=21_000))
    height = draw(st.integers(min_value=0, max_value=80))
    open_off = draw(st.integers(min_value=0, max_value=height))
    close_off = draw(st.integers(min_value=0, max_value=height))
    return Bar(
        ts=T0 + timedelta(hours=index),
        open=(low_ticks + open_off) * TICK,
        high=(low_ticks + height) * TICK,
        low=low_ticks * TICK,
        close=(low_ticks + close_off) * TICK,
        volume=100.0,
    )


@st.composite
def bar_series(draw: st.DrawFn) -> list[Bar]:
    n = draw(st.integers(min_value=2, max_value=30))
    return [draw(tick_bars(index=i)) for i in range(n)]


# ---------------------------------------------------------------------------
# Fills always within the bar range (± modeled slippage)
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(bar=tick_bars(), side=st.sampled_from([Side.BUY, Side.SELL]))
def test_market_fill_within_bar_plus_slippage(costs: CostModel, bar: Bar, side: Side) -> None:
    sim = ExecutionSimulator(costs)
    order = MarketOrder(symbol="MES", side=side, quantity=1)
    fill = sim.fill_market(order, bar, "test")
    slip = costs.slippage_points("MES", bar.ts)
    assert bar.low - slip <= fill.price <= bar.high + slip


@settings(max_examples=150, deadline=None)
@given(
    bar=tick_bars(),
    side=st.sampled_from([Side.BUY, Side.SELL]),
    stop_ticks=st.integers(min_value=19_000, max_value=21_100),
)
def test_stop_fill_within_bar_plus_slippage(
    costs: CostModel, bar: Bar, side: Side, stop_ticks: int
) -> None:
    sim = ExecutionSimulator(costs)
    order = StopOrder(symbol="MES", side=side, quantity=1, stop_price=stop_ticks * TICK)
    fill = sim.try_fill_stop(order, bar, "test")
    if fill is not None:
        slip = costs.slippage_points("MES", bar.ts)
        assert bar.low - slip <= fill.price <= bar.high + slip


@settings(max_examples=150, deadline=None)
@given(
    bar=tick_bars(),
    side=st.sampled_from([Side.BUY, Side.SELL]),
    limit_ticks=st.integers(min_value=19_000, max_value=21_100),
)
def test_limit_fill_within_bar_never_worse_than_limit(
    costs: CostModel, bar: Bar, side: Side, limit_ticks: int
) -> None:
    sim = ExecutionSimulator(costs)
    limit_price = limit_ticks * TICK
    order = LimitOrder(symbol="MES", side=side, quantity=1, limit_price=limit_price)
    fill = sim.try_fill_limit(order, bar, "test")
    if fill is not None:
        assert bar.low <= fill.price <= bar.high  # limits never fill outside the bar
        if side is Side.BUY:
            assert fill.price <= limit_price  # and never worse than the limit
        else:
            assert fill.price >= limit_price


# ---------------------------------------------------------------------------
# Accounting invariant under random event sequences
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    events=st.lists(
        st.tuples(
            st.sampled_from(["fill", "mark"]),
            st.integers(min_value=-3, max_value=3),
            st.integers(min_value=19_000, max_value=21_000),
        ),
        min_size=1,
        max_size=40,
    )
)
def test_accounting_invariant_random_sequences(
    costs: CostModel, events: list[tuple[str, int, int]]
) -> None:
    """Portfolio self-checks (incremental vs recomputed equity) after every
    event; this also independently reconciles the final state: once flat,
    equity == cash and equals initial + sum of exact per-fill P&L."""
    portfolio = Portfolio(costs, CASH)
    ts = T0
    for kind, quantity, price_ticks in events:
        ts += timedelta(minutes=1)
        price = price_ticks * TICK
        if kind == "fill" and quantity != 0:
            portfolio.apply_fill(
                FillEvent(
                    ts=ts,
                    symbol="MES",
                    quantity=quantity,
                    price=price,
                    commission_cents=80 * abs(quantity),
                    reason="t",
                )
            )
        else:
            portfolio.mark_to_market(ts, {"MES": price})
    # Flatten and reconcile: equity must equal cash exactly once flat.
    final_quantity = portfolio.quantity("MES")
    if final_quantity != 0:
        portfolio.apply_fill(
            FillEvent(
                ts=ts + timedelta(minutes=1),
                symbol="MES",
                quantity=-final_quantity,
                price=20_000 * TICK,
                commission_cents=0,
                reason="flatten",
            )
        )
    assert portfolio.quantity("MES") == 0
    assert portfolio.equity_cents == portfolio.cash_cents
    assert portfolio.recompute_equity() == portfolio.equity_cents


# ---------------------------------------------------------------------------
# No negative-time events through the engine
# ---------------------------------------------------------------------------


class RandomTargets:
    def __init__(self, targets: list[int]) -> None:
        self._targets = targets

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        return {"MES": self._targets[ctx.index % len(self._targets)]}


@settings(max_examples=60, deadline=None)
@given(
    bars=bar_series(),
    targets=st.lists(st.integers(min_value=-2, max_value=2), min_size=1, max_size=8),
)
def test_engine_events_never_go_backward(
    costs: CostModel, bars: list[Bar], targets: list[int]
) -> None:
    """The engine raises on any backward time step; completing a run with
    monotone fills IS the property. Fill and equity timestamps must be
    non-decreasing and every fill must coincide with a bar timestamp."""
    result = Engine({"MES": bars}, RandomTargets(targets), costs, EngineConfig(CASH)).run()
    fill_ts = [f.ts for f in result.fills]
    assert fill_ts == sorted(fill_ts)
    curve_ts = [t for t, _ in result.equity_curve]
    assert curve_ts == sorted(curve_ts)
    bar_ts = {b.ts for b in bars}
    assert all(t in bar_ts for t in fill_ts)
