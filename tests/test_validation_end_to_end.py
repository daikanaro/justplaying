"""Slice 4.3 acceptance: an end-to-end run on a dummy strategy produces ALL
the battery artifacts, and every run along the way landed in the experiment
log (the TRUE trial count)."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.validation_helpers import FlipStrategy, trend_bars

from qt.backtest.engine import EngineConfig, Strategy
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel
from qt.validation.deflated_sharpe import deflated_sharpe
from qt.validation.era_split import Era, run_era_splits
from qt.validation.experiment_log import ExperimentLog
from qt.validation.heatmap import HeatmapData, assess_plateau, render_heatmap
from qt.validation.mc_reshuffle import reshuffle_drawdowns
from qt.validation.runner import run_experiment
from qt.validation.slippage_stress import run_slippage_stress
from qt.validation.walk_forward import run_walk_forward

CASH = 100_000_000
BARS_PER_YEAR = 252.0 * 23
REPO_ROOT = Path(__file__).resolve().parent.parent


def factory(params: dict[str, Any]) -> Strategy:
    return FlipStrategy("MES", hold=params.get("hold", 5))


@pytest.mark.parametrize("dummy", ["end-to-end"])
def test_full_battery_produces_all_artifacts(tmp_path: Path, config_dir: Path, dummy: str) -> None:
    instruments = load_config(config_dir / "instruments.yaml", InstrumentsConfig)
    costs = CostModel(instruments)
    bars = {"MES": trend_bars(240, step=0.5)}
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    engine_config = EngineConfig(CASH)

    with ExperimentLog(tmp_path / "experiments.sqlite") as log:
        # 1. Baseline run + metrics.json
        baseline = run_experiment(
            log,
            "dummy",
            {"hold": 5},
            bars,
            factory({"hold": 5}),
            costs,
            engine_config,
            BARS_PER_YEAR,
        )
        (artifacts / "metrics.json").write_text(
            json.dumps(baseline.metrics.as_dict(), indent=2), encoding="utf-8"
        )
        assert baseline.metrics.n_trades > 5

        # 2. Walk-forward + wf.json
        wf = run_walk_forward(
            log,
            "dummy",
            bars,
            [{"hold": 4}, {"hold": 6}],
            factory,
            costs,
            engine_config,
            BARS_PER_YEAR,
            train_bars=120,
            test_bars=60,
        )
        (artifacts / "wf.json").write_text(
            json.dumps(
                [
                    {"params": w.chosen_params, "oos_sharpe": w.oos.metrics.sharpe}
                    for w in wf.windows
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        assert wf.windows and wf.oos_trades

        # 3. Heatmap + plateau assessment
        grid_cells = [
            [
                run_experiment(
                    log,
                    "dummy/grid",
                    {"hold": h, "spread": s},
                    bars,
                    factory({"hold": h}),
                    costs,
                    engine_config,
                    BARS_PER_YEAR,
                ).metrics.sharpe
                for s in (1, 2)
            ]
            for h in (4, 5, 6)
        ]
        heatmap = HeatmapData("hold", "spread", [4.0, 5.0, 6.0], [1.0, 2.0], grid_cells)
        render_heatmap(heatmap, "dummy sharpe", artifacts / "heatmap.png")
        assessment = assess_plateau(heatmap)

        # 4. MC reshuffle (small path count for CI; production default is 10k)
        mc = reshuffle_drawdowns(baseline.trades, n_paths=1000, seed=11)
        (artifacts / "mc.json").write_text(
            json.dumps(
                {
                    "observed": mc.observed_max_drawdown_cents,
                    "p95": mc.drawdown_p95_cents,
                    "worst": mc.drawdown_worst_cents,
                    "observed_percentile": mc.observed_percentile,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # 5. Slippage stress x1/x2/x3
        stress = run_slippage_stress(
            log,
            "dummy",
            {"hold": 5},
            bars,
            factory,
            instruments,
            engine_config,
            BARS_PER_YEAR,
        )
        (artifacts / "stress.json").write_text(
            json.dumps({str(m): r.metrics.mean_trade_cents for m, r in stress.items()}, indent=2),
            encoding="utf-8",
        )

        # 6. Era splits
        eras = run_era_splits(
            log,
            "dummy",
            {"hold": 5},
            bars,
            factory,
            costs,
            engine_config,
            BARS_PER_YEAR,
            eras=[Era("2024", *_year_2024())],
            min_bars=50,
        )
        (artifacts / "eras.json").write_text(
            json.dumps(
                [
                    {
                        "era": e.era.name,
                        "n_bars": e.n_bars,
                        "sharpe": e.result.metrics.sharpe if e.result else None,
                    }
                    for e in eras
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        # 7. Deflated Sharpe with the TRUE trial count from the log
        n_trials = log.trial_count()
        sharpes = [r.metrics["sharpe"] for r in log.records()]
        mean_sr = sum(sharpes) / len(sharpes)
        sr_variance = sum((s - mean_sr) ** 2 for s in sharpes) / max(1, len(sharpes) - 1)
        dsr = deflated_sharpe(
            sharpe=baseline.metrics.sharpe / (BARS_PER_YEAR**0.5),  # de-annualized
            n_obs=baseline.metrics.n_bars,
            n_trials=max(2, n_trials),
            sr_variance=max(1e-9, sr_variance / BARS_PER_YEAR),
        )
        (artifacts / "deflated_sharpe.json").write_text(
            json.dumps({"n_trials": n_trials, "dsr": dsr}, indent=2), encoding="utf-8"
        )

        # The log counted every single run above — no opt-out anywhere.
        # 1 baseline + WF (2 windows x 2 grid + 2 oos = 6) + 6 heatmap cells
        # + 3 stress + 1 era = 17.
        assert n_trials == 17

    for name in (
        "metrics.json",
        "wf.json",
        "heatmap.png",
        "mc.json",
        "stress.json",
        "eras.json",
        "deflated_sharpe.json",
    ):
        artifact = artifacts / name
        assert artifact.is_file() and artifact.stat().st_size > 0, f"missing artifact {name}"
    assert 0.0 <= dsr <= 1.0
    assert assessment.best_cell is not None


def _year_2024() -> tuple[date, date]:
    return date(2024, 1, 1), date(2024, 12, 31)


def test_memo_template_exists_with_required_sections() -> None:
    template = (REPO_ROOT / "research" / "memo_template.md").read_text(encoding="utf-8")
    for required in (
        "Mechanism claim",
        "Validation battery",
        "Tail metrics",
        "Deflated Sharpe",
        "WORSE governs",
        "Verdict (OWNER ONLY)",
        "DEPLOY",
        "PARK",
    ):
        assert required in template, f"memo template missing section: {required}"
