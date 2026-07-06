"""Slippage-stress and era-split runner tests."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.validation_helpers import FlipStrategy, trend_bars

from qt.backtest.engine import EngineConfig, Strategy
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel
from qt.validation.era_split import DEFAULT_ERAS, Era, run_era_splits, split_by_era
from qt.validation.experiment_log import ExperimentLog
from qt.validation.slippage_stress import run_slippage_stress

CASH = 100_000_000


@pytest.fixture(scope="module")
def instruments(config_dir: Path) -> InstrumentsConfig:
    return load_config(config_dir / "instruments.yaml", InstrumentsConfig)


def flip_factory(params: dict[str, Any]) -> Strategy:
    return FlipStrategy("MES", hold=5)


def test_stress_runs_all_configured_multipliers_and_costs_bite(
    tmp_path: Path, instruments: InstrumentsConfig
) -> None:
    bars = {"MES": trend_bars(80, step=0.5)}
    with ExperimentLog(tmp_path / "log.sqlite") as log:
        results = run_slippage_stress(
            log,
            "dummy",
            {"hold": 5},
            bars,
            flip_factory,
            instruments,
            EngineConfig(CASH),
            bars_per_year=252.0 * 23,
        )
        assert sorted(results) == [1, 2, 3]  # schema guarantees x1/x2/x3 present
        assert log.trial_count() == 3
        assert log.trial_count("dummy/slip-x3") == 1
    means = [results[m].metrics.mean_trade_cents for m in (1, 2, 3)]
    assert means[0] > means[1] > means[2]  # every extra slippage tick costs money
    # Same trades, same signals — only the fills differ.
    counts = {results[m].metrics.n_trades for m in (1, 2, 3)}
    assert len(counts) == 1


def test_split_by_era_boundaries() -> None:
    bars = {
        "MES": trend_bars(5, start_ts=datetime(2012, 12, 29, 15, 0, tzinfo=UTC), bar_hours=24)
    }  # daily bars: Dec 29, 30, 31, Jan 1, Jan 2
    sliced = split_by_era(bars, DEFAULT_ERAS)
    assert len(sliced["pre-2013"]["MES"]) == 3
    assert len(sliced["2013-2019"]["MES"]) == 2
    assert len(sliced["2020-present"]["MES"]) == 0


def test_era_runner_skips_thin_eras_and_labels_provisional(
    tmp_path: Path, instruments: InstrumentsConfig
) -> None:
    eras = [
        Era("ancient", date(2000, 1, 1), date(2000, 12, 31)),  # no data -> skipped
        Era("recent", date(2024, 1, 1), date(2024, 12, 31), provisional=True),
    ]
    bars = {"MES": trend_bars(200, step=0.5)}  # hourly bars in Jan 2024
    with ExperimentLog(tmp_path / "log.sqlite") as log:
        results = run_era_splits(
            log,
            "dummy",
            {},
            bars,
            flip_factory,
            CostModel(instruments),
            EngineConfig(CASH),
            bars_per_year=252.0 * 23,
            eras=eras,
        )
        assert results[0].result is None  # too thin to run
        assert results[0].n_bars == 0
        assert results[1].result is not None
        assert results[1].n_bars == 200
        # PROVISIONAL data is labeled in the log, per §1.
        assert log.trial_count("dummy/era-recent-PROVISIONAL") == 1
        assert log.trial_count() == 1
