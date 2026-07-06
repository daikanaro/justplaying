"""Walk-forward runner (§3 validation battery).

Rolling windows: optimize on train, evaluate out-of-sample on the adjacent
test window, roll forward by the test length. Every train-cell evaluation and
every OOS run goes through run_experiment, so the experiment log counts every
trial — that is the entire point.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qt.backtest.engine import EngineConfig, Strategy
from qt.backtest.events import Bar
from qt.costs.model import CostModel
from qt.validation.experiment_log import ExperimentLog
from qt.validation.metrics import Metrics
from qt.validation.runner import ExperimentResult, run_experiment

StrategyFactory = Callable[[dict[str, Any]], Strategy]
Selector = Callable[[Metrics], float]


def sharpe_selector(metrics: Metrics) -> float:
    return metrics.sharpe


@dataclass(frozen=True)
class Window:
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive


@dataclass(frozen=True)
class WindowResult:
    window: Window
    chosen_params: dict[str, Any]
    train_score: float
    oos: ExperimentResult


@dataclass(frozen=True)
class WalkForwardResult:
    windows: list[WindowResult]
    oos_trades: list[int]  # stitched out-of-sample trades, chronological


def walk_forward_windows(n_bars: int, train_bars: int, test_bars: int) -> list[Window]:
    if train_bars < 1 or test_bars < 1:
        msg = "train_bars and test_bars must be >= 1"
        raise ValueError(msg)
    if train_bars + test_bars > n_bars:
        msg = f"not enough bars ({n_bars}) for train {train_bars} + test {test_bars}"
        raise ValueError(msg)
    windows = []
    start = 0
    while start + train_bars + test_bars <= n_bars:
        windows.append(
            Window(
                train_start=start,
                train_end=start + train_bars,
                test_start=start + train_bars,
                test_end=start + train_bars + test_bars,
            )
        )
        start += test_bars
    return windows


def _slice_bars(bars: dict[str, list[Bar]], start: int, end: int) -> dict[str, list[Bar]]:
    return {symbol: series[start:end] for symbol, series in bars.items()}


def run_walk_forward(
    log: ExperimentLog,
    strategy_name: str,
    bars: dict[str, list[Bar]],
    param_grid: list[dict[str, Any]],
    strategy_factory: StrategyFactory,
    costs: CostModel,
    engine_config: EngineConfig,
    bars_per_year: float,
    train_bars: int,
    test_bars: int,
    selector: Selector = sharpe_selector,
) -> WalkForwardResult:
    if not param_grid:
        msg = "param_grid must not be empty"
        raise ValueError(msg)
    n_bars = len(next(iter(bars.values())))
    windows = walk_forward_windows(n_bars, train_bars, test_bars)
    results: list[WindowResult] = []
    oos_trades: list[int] = []
    for window in windows:
        train_slice = _slice_bars(bars, window.train_start, window.train_end)
        best_params: dict[str, Any] | None = None
        best_score = float("-inf")
        for params in param_grid:
            trial = run_experiment(
                log,
                f"{strategy_name}/wf-train",
                params,
                train_slice,
                strategy_factory(params),
                costs,
                engine_config,
                bars_per_year,
            )
            score = selector(trial.metrics)
            if score > best_score:
                best_score = score
                best_params = params
        assert best_params is not None
        test_slice = _slice_bars(bars, window.test_start, window.test_end)
        oos = run_experiment(
            log,
            f"{strategy_name}/wf-oos",
            best_params,
            test_slice,
            strategy_factory(best_params),
            costs,
            engine_config,
            bars_per_year,
        )
        results.append(
            WindowResult(window=window, chosen_params=best_params, train_score=best_score, oos=oos)
        )
        oos_trades.extend(oos.trades)
    return WalkForwardResult(windows=results, oos_trades=oos_trades)
