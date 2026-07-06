"""Run the full §3 validation battery for S1 and S2 on curated data.

Produces, per strategy, under research/<strategy>/:
  metrics.json, wf.json, heatmap.png, mc.json, stress.json, eras.json,
  deflated_sharpe.json, and (S2) fill_modes.json — the memo inputs.
Every run appends to research/experiments.sqlite (no opt-out).

BLOCKED until the slice 4.1 data pipeline has produced data/curated/ series
(IBKR owner items, §6) and VIX has been fetched. This script checks and says
exactly what is missing rather than fabricating anything.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from itertools import product
from pathlib import Path
from typing import Any

import polars as pl

from qt.backtest.engine import EngineConfig, Strategy
from qt.backtest.events import Bar
from qt.config import (
    DataConfig,
    InstrumentsConfig,
    RiskConfig,
    StrategiesConfig,
    load_config,
)
from qt.costs.model import CostModel
from qt.data.events import load_events
from qt.strategies.s1_trend_breakout import S1TrendBreakout
from qt.strategies.s2_mr_rsi2 import S2MeanReversion
from qt.validation.deflated_sharpe import deflated_sharpe
from qt.validation.era_split import run_era_splits
from qt.validation.experiment_log import ExperimentLog
from qt.validation.heatmap import HeatmapData, assess_plateau, render_heatmap
from qt.validation.mc_reshuffle import reshuffle_drawdowns
from qt.validation.runner import run_experiment
from qt.validation.slippage_stress import run_slippage_stress
from qt.validation.walk_forward import run_walk_forward

REPO_ROOT = Path(__file__).resolve().parent.parent
CASH = 10_000_000  # $100k paper-scale
HOURLY_BARS_PER_YEAR = 252.0 * 23.0
DAILY_BARS_PER_YEAR = 252.0


def load_continuous(curated: Path, symbol: str, timeframe: str) -> list[Bar]:
    path = curated / symbol / f"continuous_{timeframe}.parquet"
    if not path.is_file():
        msg = (
            f"missing curated series {path} — run scripts/download_ibkr_history.py and "
            "scripts/build_continuous.py first (OWNER items §6: IBKR paper login + "
            "market-data subscription)"
        )
        raise FileNotFoundError(msg)
    df = pl.read_parquet(path).sort("ts")
    return [
        Bar(
            ts=r["ts"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
        )
        for r in df.iter_rows(named=True)
    ]


def load_vix_provider(curated: Path) -> dict[date, float]:
    path = curated / "vix" / "vix_daily.parquet"
    if not path.is_file():
        msg = f"missing VIX series {path} — run scripts/fetch_vix.py first"
        raise FileNotFoundError(msg)
    df = pl.read_parquet(path)
    return dict(zip(df.get_column("date").to_list(), df.get_column("close").to_list(), strict=True))


def specs(instruments: InstrumentsConfig) -> dict[str, tuple[float, float]]:
    return {
        symbol: (spec.dollars_per_point, spec.tick_size)
        for symbol, spec in instruments.instruments.items()
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def battery(  # noqa: PLR0913 - top-level orchestration
    log: ExperimentLog,
    name: str,
    bars: dict[str, list[Bar]],
    factory: Any,
    grid: list[dict[str, Any]],
    instruments: InstrumentsConfig,
    bars_per_year: float,
    out_dir: Path,
    engine_config: EngineConfig,
) -> None:
    costs = CostModel(instruments)
    base_params = grid[0]
    baseline = run_experiment(
        log, name, base_params, bars, factory(base_params), costs, engine_config, bars_per_year
    )
    write_json(out_dir / "metrics.json", baseline.metrics.as_dict())

    n_bars = len(next(iter(bars.values())))
    wf = run_walk_forward(
        log,
        name,
        bars,
        grid,
        factory,
        costs,
        engine_config,
        bars_per_year,
        train_bars=n_bars // 2,
        test_bars=n_bars // 4,
    )
    write_json(
        out_dir / "wf.json",
        [{"params": w.chosen_params, "oos_sharpe": w.oos.metrics.sharpe} for w in wf.windows],
    )

    if baseline.trades:
        mc = reshuffle_drawdowns(baseline.trades, n_paths=10_000)
        write_json(
            out_dir / "mc.json",
            {
                "observed": mc.observed_max_drawdown_cents,
                "p50": mc.drawdown_p50_cents,
                "p95": mc.drawdown_p95_cents,
                "worst": mc.drawdown_worst_cents,
                "observed_percentile": mc.observed_percentile,
            },
        )

    stress = run_slippage_stress(
        log, name, base_params, bars, factory, instruments, engine_config, bars_per_year
    )
    write_json(
        out_dir / "stress.json",
        {str(m): r.metrics.as_dict() for m, r in stress.items()},
    )

    eras = run_era_splits(
        log, name, base_params, bars, factory, costs, engine_config, bars_per_year
    )
    write_json(
        out_dir / "eras.json",
        [
            {
                "era": e.era.name,
                "n_bars": e.n_bars,
                "provisional": e.era.provisional,
                "metrics": e.result.metrics.as_dict() if e.result else None,
            }
            for e in eras
        ],
    )

    n_trials = log.trial_count()
    sharpes = [r.metrics.get("sharpe", 0.0) for r in log.records()]
    mean_sr = sum(sharpes) / len(sharpes)
    sr_var = sum((s - mean_sr) ** 2 for s in sharpes) / max(1, len(sharpes) - 1)
    dsr = deflated_sharpe(
        sharpe=baseline.metrics.sharpe / (bars_per_year**0.5),
        n_obs=baseline.metrics.n_bars,
        n_trials=max(2, n_trials),
        sr_variance=max(1e-9, sr_var / bars_per_year),
    )
    write_json(out_dir / "deflated_sharpe.json", {"true_trial_count": n_trials, "dsr": dsr})


def main() -> int:
    config_dir = REPO_ROOT / "config"
    instruments = load_config(config_dir / "instruments.yaml", InstrumentsConfig)
    risk = load_config(config_dir / "risk.yaml", RiskConfig)
    strategies = load_config(config_dir / "strategies.yaml", StrategiesConfig)
    data_cfg = load_config(config_dir / "data.yaml", DataConfig)
    curated = REPO_ROOT / Path(data_cfg.paths.curated_dir)

    try:
        s1_bars = {
            s: load_continuous(curated, s, "1hour")
            for s in strategies.s1_trend_breakout.tf_h.symbols
        }
        s2_bars = {s: load_continuous(curated, s, "1day") for s in strategies.s2_mr_rsi2.symbols}
        vix_by_date = load_vix_provider(curated)
    except FileNotFoundError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    events = load_events(REPO_ROOT / Path(data_cfg.paths.calendar_file))
    if not events:
        print("WARNING: events.csv is empty — blackout gates are inert (OWNER item §6)")

    log = ExperimentLog(REPO_ROOT / "research" / "experiments.sqlite")
    spec_map = specs(instruments)
    s1_params = strategies.s1_trend_breakout.tf_h
    s1_research = strategies.s1_trend_breakout.research_grid

    def s1_factory(params: dict[str, Any]) -> Strategy:
        merged = s1_params.model_copy(
            update={"donchian_n": params["donchian_n"], "atr_stop_k": params["atr_stop_k"]}
        )
        return S1TrendBreakout(merged, risk, spec_map, events)

    s1_grid = [
        {"donchian_n": n, "atr_stop_k": k}
        for n, k in product(s1_research.donchian_n, s1_research.atr_stop_k)
    ]
    with log:
        battery(
            log,
            "S1-TF-H",
            s1_bars,
            s1_factory,
            s1_grid,
            instruments,
            HOURLY_BARS_PER_YEAR,
            REPO_ROOT / "research" / "s1_trend_breakout",
            EngineConfig(CASH),
        )
        # S1 heatmap over the full research grid, sharpe per cell.
        cells = [
            [
                run_experiment(
                    log,
                    "S1-TF-H/grid",
                    {"donchian_n": n, "atr_stop_k": k},
                    s1_bars,
                    s1_factory({"donchian_n": n, "atr_stop_k": k}),
                    CostModel(instruments),
                    EngineConfig(CASH),
                    HOURLY_BARS_PER_YEAR,
                ).metrics.sharpe
                for k in s1_research.atr_stop_k
            ]
            for n in s1_research.donchian_n
        ]
        heatmap = HeatmapData(
            "donchian_n",
            "atr_stop_k",
            [float(n) for n in s1_research.donchian_n],
            list(s1_research.atr_stop_k),
            cells,
        )
        render_heatmap(
            heatmap, "S1 TF-H sharpe", REPO_ROOT / "research" / "s1_trend_breakout" / "heatmap.png"
        )
        write_json(
            REPO_ROOT / "research" / "s1_trend_breakout" / "plateau.json",
            {"assessment": str(assess_plateau(heatmap))},
        )

        def s2_factory(params: dict[str, Any]) -> Strategy:
            return S2MeanReversion(strategies.s2_mr_rsi2, risk, spec_map, vix_by_date.get, events)

        s2_grid: list[dict[str, Any]] = [{}]
        for mode, engine_config in (
            ("next_open", EngineConfig(CASH)),
            ("same_close_LOOKAHEAD", EngineConfig(CASH, same_close_fills=True)),
        ):
            battery(
                log,
                f"S2-{mode}",
                s2_bars,
                s2_factory,
                s2_grid,
                instruments,
                DAILY_BARS_PER_YEAR,
                REPO_ROOT / "research" / "s2_mr_rsi2" / mode,
                engine_config,
            )
        # §3: the WORSE of the two fill modes governs all decisions.
        modes = {}
        for mode in ("next_open", "same_close_LOOKAHEAD"):
            metrics_file = REPO_ROOT / "research" / "s2_mr_rsi2" / mode / "metrics.json"
            modes[mode] = json.loads(metrics_file.read_text(encoding="utf-8"))
        governing = min(modes, key=lambda m: modes[m]["sharpe"])
        write_json(
            REPO_ROOT / "research" / "s2_mr_rsi2" / "fill_modes.json",
            {"modes": modes, "governing_mode_worse_of_two": governing},
        )
    print("battery complete — artifacts under research/; log: research/experiments.sqlite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
