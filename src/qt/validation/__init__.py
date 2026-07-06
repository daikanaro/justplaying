"""Validation harness (BUILD_PLAN slice 4.3).

Research entry point: every backtest run in this package goes through
:func:`qt.validation.runner.run_experiment`, which REQUIRES an ExperimentLog
and appends unconditionally — there is no opt-out parameter, because deflated
Sharpe needs the TRUE trial count (CLAUDE.md). Direct qt.backtest.Engine use
is for unit tests only, never for research.
"""

from qt.validation.experiment_log import ExperimentLog
from qt.validation.runner import ExperimentResult, run_experiment

__all__ = ["ExperimentLog", "ExperimentResult", "run_experiment"]
