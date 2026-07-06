"""The sanctioned research entry point: run a backtest AND log it, atomically.

``run_experiment`` has no ``log=None`` escape hatch by design — the log
parameter is required and the append is unconditional (CLAUDE.md: no opt-out;
deflated Sharpe needs the TRUE trial count).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qt.backtest.engine import BacktestResult, Engine, EngineConfig, Strategy
from qt.backtest.events import Bar
from qt.costs.model import CostModel
from qt.validation.experiment_log import ExperimentLog
from qt.validation.metrics import Metrics, compute_metrics
from qt.validation.trades import round_trips


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: int
    metrics: Metrics
    trades: list[int]
    backtest: BacktestResult


def run_experiment(
    log: ExperimentLog,
    strategy_name: str,
    params: dict[str, Any],
    bars: dict[str, list[Bar]],
    strategy: Strategy,
    costs: CostModel,
    engine_config: EngineConfig,
    bars_per_year: float,
) -> ExperimentResult:
    result = Engine(bars, strategy, costs, engine_config).run()
    trades = round_trips(result.fills, costs)
    metrics = compute_metrics(result.equity_curve, trades, bars_per_year)
    timestamps = [b.ts for b in next(iter(bars.values()))]
    experiment_id = log.append(
        strategy=strategy_name,
        params=params,
        symbols=sorted(bars),
        span_start=timestamps[0],
        span_end=timestamps[-1],
        n_bars=len(timestamps),
        n_trades=len(trades),
        metrics=metrics.as_dict(),
    )
    return ExperimentResult(
        experiment_id=experiment_id, metrics=metrics, trades=trades, backtest=result
    )
