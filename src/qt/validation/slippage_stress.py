"""Slippage stress runner: x1/x2/x3 are MANDATORY in validation (§1).

The multipliers come from config (instruments.yaml slippage.stress_multipliers,
schema-enforced to include 1, 2, 3) — not from a call-site argument someone
could trim.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qt.backtest.engine import EngineConfig, Strategy
from qt.backtest.events import Bar
from qt.config.schemas import InstrumentsConfig
from qt.costs.model import CostModel
from qt.validation.experiment_log import ExperimentLog
from qt.validation.runner import ExperimentResult, run_experiment


def run_slippage_stress(
    log: ExperimentLog,
    strategy_name: str,
    params: dict[str, Any],
    bars: dict[str, list[Bar]],
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    instruments: InstrumentsConfig,
    engine_config: EngineConfig,
    bars_per_year: float,
) -> dict[int, ExperimentResult]:
    """One run per configured stress multiplier; keyed by multiplier."""
    results: dict[int, ExperimentResult] = {}
    for multiplier in instruments.slippage.stress_multipliers:
        results[multiplier] = run_experiment(
            log,
            f"{strategy_name}/slip-x{multiplier}",
            {**params, "slippage_stress": multiplier},
            bars,
            strategy_factory(params),
            CostModel(instruments, stress_multiplier=multiplier),
            engine_config,
            bars_per_year,
        )
    return results
