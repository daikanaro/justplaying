"""Metrics + production round-trip extraction tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qt.backtest.events import FillEvent
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel
from qt.validation.metrics import (
    compute_metrics,
    es95_cents,
    max_drawdown_pct,
    max_losing_cluster,
    sharpe_ratio,
)
from qt.validation.trades import round_trips

T0 = datetime(2024, 7, 8, 15, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def costs(config_dir: Path) -> CostModel:
    return CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))


def fill(i: int, quantity: int, price: float, commission: int) -> FillEvent:
    return FillEvent(
        ts=T0 + timedelta(hours=i),
        symbol="MES",
        quantity=quantity,
        price=price,
        commission_cents=commission,
        reason="t",
    )


def test_round_trips_ka2_trades(costs: CostModel) -> None:
    """The KA-2 fill stream must decompose into its two hand-computed trades."""
    fills = [
        fill(0, 2, 5003.25, 160),
        fill(1, -2, 4995.75, 160),  # -30 ticks x 125c x 2 - 320c = -7,820
        fill(2, -1, 4986.75, 80),
        fill(3, 1, 4978.25, 80),  # +34 ticks x 125c - 160c = +4,090
    ]
    assert round_trips(fills, costs) == [-7820, 4090]


def test_round_trips_reversal_splits(costs: CostModel) -> None:
    fills = [
        fill(0, 1, 5000.00, 80),
        fill(1, -2, 5001.00, 160),  # closes +1 (+4 ticks - 80 - 80) AND opens -1
        fill(2, 1, 5000.00, 80),  # covers -1: +4 ticks - 80 - 80
    ]
    # Trade 1: +500 - 160 = +340. Trade 2: +500 - 160 = +340.
    assert round_trips(fills, costs) == [340, 340]


def test_round_trips_open_tail_ignored(costs: CostModel) -> None:
    fills = [fill(0, 1, 5000.00, 80)]
    assert round_trips(fills, costs) == []


def test_round_trips_scale_in_fifo(costs: CostModel) -> None:
    fills = [
        fill(0, 1, 5000.00, 80),
        fill(1, 1, 5001.00, 80),  # add
        fill(2, -2, 5002.00, 160),  # close both: (+8 ticks) + (+4 ticks) x 125 - 320
    ]
    assert round_trips(fills, costs) == [(8 + 4) * 125 - 320]


def test_sharpe_ratio_known_series() -> None:
    equity = [100_000, 101_000, 102_010]  # two +1% returns, zero variance -> 0 by rule
    assert sharpe_ratio(equity, 252) == 0.0
    rising_choppy = [100_000, 102_000, 101_000, 103_000, 102_500]
    assert sharpe_ratio(rising_choppy, 252) > 0.0
    assert sharpe_ratio(list(reversed(rising_choppy)), 252) < 0.0
    assert sharpe_ratio([100_000], 252) == 0.0


def test_max_drawdown_pct() -> None:
    assert max_drawdown_pct([100, 120, 90, 130]) == pytest.approx(-25.0)  # 120 -> 90
    assert max_drawdown_pct([100, 110, 120]) == 0.0


def test_es95_is_tail_mean() -> None:
    trades = list(range(-100, 0))  # -100..-1: worst 5% = [-100..-96], mean -98
    assert es95_cents(trades) == pytest.approx(-98.0)
    assert es95_cents([5]) == 5.0
    assert es95_cents([]) == 0.0


def test_max_losing_cluster() -> None:
    assert max_losing_cluster([-1, -1, 5, -1, -1, -1, 2]) == 3
    assert max_losing_cluster([1, 2, 3]) == 0
    assert max_losing_cluster([]) == 0


def test_compute_metrics_integration() -> None:
    curve = [(T0 + timedelta(days=i), e) for i, e in enumerate([100_000, 101_000, 99_000, 102_000])]
    metrics = compute_metrics(curve, trades=[1000, -2000, 3000], bars_per_year=252)
    assert metrics.n_bars == 4
    assert metrics.n_trades == 3
    assert metrics.total_return_pct == pytest.approx(2.0)
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.worst_trade_cents == -2000
    assert metrics.worst_day_cents == -2000  # 101,000 -> 99,000
    assert metrics.max_losing_cluster == 1
    payload = metrics.as_dict()
    assert set(payload) == {
        "n_bars",
        "n_trades",
        "total_return_pct",
        "sharpe",
        "max_drawdown_pct",
        "win_rate",
        "mean_trade_cents",
        "es95_cents",
        "worst_trade_cents",
        "worst_day_cents",
        "max_losing_cluster",
    }
