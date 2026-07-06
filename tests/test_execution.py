"""Execution simulator tests: §4 fill rules, one bar at a time."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.backtest.events import Bar
from qt.backtest.execution import ExecutionConfig, ExecutionSimulator
from qt.backtest.orders import LimitOrder, MarketOrder, Side, StopOrder
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel

RTH_TS = datetime(2024, 7, 8, 15, 0, tzinfo=UTC)  # 1-tick slippage session
ETH_TS = datetime(2024, 7, 8, 2, 0, tzinfo=UTC)  # 2-tick slippage session


@pytest.fixture(scope="module")
def sim(config_dir: Path) -> ExecutionSimulator:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    return ExecutionSimulator(costs)


def bar(ts: datetime, o: float, h: float, lo: float, c: float) -> Bar:
    return Bar(ts=ts, open=o, high=h, low=lo, close=c, volume=100.0)


def test_market_buy_pays_slippage_rth(sim: ExecutionSimulator) -> None:
    order = MarketOrder(symbol="MES", side=Side.BUY, quantity=2)
    fill = sim.fill_market(order, bar(RTH_TS, 5000.00, 5005, 4995, 5002), "entry")
    assert fill.price == pytest.approx(5000.25)  # open + 1 tick
    assert fill.quantity == 2
    assert fill.commission_cents == 160
    assert order.remaining == 0


def test_market_sell_eth_double_slippage(sim: ExecutionSimulator) -> None:
    order = MarketOrder(symbol="MES", side=Side.SELL, quantity=1)
    fill = sim.fill_market(order, bar(ETH_TS, 5000.00, 5005, 4995, 5002), "exit")
    assert fill.price == pytest.approx(4999.50)  # open - 2 ticks
    assert fill.quantity == -1


def test_sell_stop_touch_fills_at_stop(sim: ExecutionSimulator) -> None:
    order = StopOrder(symbol="MES", side=Side.SELL, quantity=1, stop_price=4998.00)
    fill = sim.try_fill_stop(order, bar(RTH_TS, 5000.00, 5001, 4997, 4999), "stop")
    assert fill is not None
    assert fill.price == pytest.approx(4997.75)  # stop - 1 tick


def test_sell_stop_gap_through_fills_at_open(sim: ExecutionSimulator) -> None:
    order = StopOrder(symbol="MES", side=Side.SELL, quantity=1, stop_price=4998.00)
    fill = sim.try_fill_stop(order, bar(RTH_TS, 4996.00, 5001, 4990, 4992), "stop")
    assert fill is not None
    assert fill.price == pytest.approx(4995.75)  # open - 1 tick: the gap is EATEN, not ignored


def test_sell_stop_untouched_no_fill(sim: ExecutionSimulator) -> None:
    order = StopOrder(symbol="MES", side=Side.SELL, quantity=1, stop_price=4998.00)
    assert sim.try_fill_stop(order, bar(RTH_TS, 5000.00, 5004, 4999, 5001), "stop") is None
    assert order.remaining == 1


def test_buy_stop_gap_through(sim: ExecutionSimulator) -> None:
    order = StopOrder(symbol="MES", side=Side.BUY, quantity=1, stop_price=5002.00)
    fill = sim.try_fill_stop(order, bar(RTH_TS, 5004.00, 5008, 5003, 5006), "stop")
    assert fill is not None
    assert fill.price == pytest.approx(5004.25)  # open + slip


def test_buy_limit_needs_trade_through(sim: ExecutionSimulator) -> None:
    order = LimitOrder(symbol="MES", side=Side.BUY, quantity=1, limit_price=4998.00)
    # Bar low EXACTLY at the limit: conservative model says unfilled.
    assert sim.try_fill_limit(order, bar(RTH_TS, 5000.00, 5001, 4998.00, 4999), "tp") is None
    # Low one tick through: filled at the limit.
    fill = sim.try_fill_limit(order, bar(RTH_TS, 5000.00, 5001, 4997.75, 4999), "tp")
    assert fill is not None
    assert fill.price == pytest.approx(4998.00)


def test_buy_limit_price_improvement_at_open(sim: ExecutionSimulator) -> None:
    order = LimitOrder(symbol="MES", side=Side.BUY, quantity=1, limit_price=4998.00)
    fill = sim.try_fill_limit(order, bar(RTH_TS, 4996.00, 5001, 4995, 4999), "tp")
    assert fill is not None
    assert fill.price == pytest.approx(4996.00)  # opened below: better price honored


def test_sell_limit_trade_through(sim: ExecutionSimulator) -> None:
    order = LimitOrder(symbol="MES", side=Side.SELL, quantity=1, limit_price=5002.00)
    assert sim.try_fill_limit(order, bar(RTH_TS, 5000.00, 5002.00, 4999, 5001), "tp") is None
    fill = sim.try_fill_limit(order, bar(RTH_TS, 5000.00, 5002.25, 4999, 5001), "tp")
    assert fill is not None
    assert fill.price == pytest.approx(5002.00)


def test_partial_fills_supported(config_dir: Path) -> None:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    sim = ExecutionSimulator(costs, ExecutionConfig(max_contracts_per_fill=2))
    order = MarketOrder(symbol="MES", side=Side.BUY, quantity=5)
    b = bar(RTH_TS, 5000.00, 5005, 4995, 5002)
    quantities = []
    while order.remaining > 0:
        quantities.append(sim.fill_market(order, b, "entry").quantity)
    assert quantities == [2, 2, 1]


def test_order_validation() -> None:
    with pytest.raises(ValueError, match="quantity"):
        MarketOrder(symbol="MES", side=Side.BUY, quantity=0)
    with pytest.raises(ValueError, match="stop_price"):
        StopOrder(symbol="MES", side=Side.SELL, quantity=1, stop_price=0.0)
    with pytest.raises(ValueError, match="max_contracts_per_fill"):
        ExecutionConfig(max_contracts_per_fill=0)
