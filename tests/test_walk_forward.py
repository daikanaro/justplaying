"""Walk-forward runner tests: window math, selection, and mandatory logging."""

from pathlib import Path
from typing import Any

import pytest
from tests.validation_helpers import HoldStrategy, trend_bars

from qt.backtest.engine import EngineConfig, Strategy
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel
from qt.validation.experiment_log import ExperimentLog
from qt.validation.walk_forward import Window, run_walk_forward, walk_forward_windows

CASH = 100_000_000


def test_window_math() -> None:
    windows = walk_forward_windows(n_bars=100, train_bars=50, test_bars=25)
    assert windows == [
        Window(train_start=0, train_end=50, test_start=50, test_end=75),
        Window(train_start=25, train_end=75, test_start=75, test_end=100),
    ]


def test_window_math_rejects_impossible() -> None:
    with pytest.raises(ValueError, match="not enough bars"):
        walk_forward_windows(n_bars=10, train_bars=8, test_bars=5)
    with pytest.raises(ValueError, match=">= 1"):
        walk_forward_windows(n_bars=10, train_bars=0, test_bars=5)


def test_walk_forward_selects_better_param_and_logs_every_trial(
    tmp_path: Path, config_dir: Path
) -> None:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    bars = {"MES": trend_bars(120, step=1.0)}  # steady uptrend
    grid: list[dict[str, Any]] = [{"direction": 1}, {"direction": -1}]

    def factory(params: dict[str, Any]) -> Strategy:
        return HoldStrategy("MES", params["direction"])

    with ExperimentLog(tmp_path / "log.sqlite") as log:
        result = run_walk_forward(
            log,
            "dummy",
            bars,
            grid,
            factory,
            costs,
            EngineConfig(CASH),
            bars_per_year=252 * 23,
            train_bars=60,
            test_bars=30,
        )
        # 2 windows x (2 train trials + 1 OOS) = 6 rows: EVERY trial is logged.
        assert log.trial_count() == 6
        assert log.trial_count("dummy/wf-train") == 4
        assert log.trial_count("dummy/wf-oos") == 2
    assert len(result.windows) == 2
    for window in result.windows:
        assert window.chosen_params == {"direction": 1}  # long wins on an uptrend
        assert window.train_score > 0


def test_walk_forward_rejects_empty_grid(tmp_path: Path, config_dir: Path) -> None:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    with ExperimentLog(tmp_path / "log.sqlite") as log, pytest.raises(ValueError, match="grid"):
        run_walk_forward(
            log,
            "dummy",
            {"MES": trend_bars(100)},
            [],
            lambda p: HoldStrategy("MES", 1),
            costs,
            EngineConfig(CASH),
            bars_per_year=252.0,
            train_bars=50,
            test_bars=25,
        )
