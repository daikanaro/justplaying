"""Era-split reporter (§3: era-split validation is mandatory for S2 and part
of the battery for S1). Default eras per the plan: <=2012 / 2013-2019 /
2020-present. Eras backed by non-IBKR provisional data must be LABELED so."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from qt.backtest.engine import EngineConfig, Strategy
from qt.backtest.events import Bar
from qt.costs.model import CostModel
from qt.validation.experiment_log import ExperimentLog
from qt.validation.runner import ExperimentResult, run_experiment


@dataclass(frozen=True)
class Era:
    name: str
    start: date  # inclusive
    end: date  # inclusive
    provisional: bool = False  # True when backed by non-vendor (e.g. Stooq) data


DEFAULT_ERAS = [
    Era("pre-2013", date(1900, 1, 1), date(2012, 12, 31)),
    Era("2013-2019", date(2013, 1, 1), date(2019, 12, 31)),
    Era("2020-present", date(2020, 1, 1), date(2100, 1, 1)),
]


@dataclass(frozen=True)
class EraResult:
    era: Era
    n_bars: int
    result: ExperimentResult | None  # None if the era has too few bars to run


def split_by_era(bars: dict[str, list[Bar]], eras: list[Era]) -> dict[str, dict[str, list[Bar]]]:
    out: dict[str, dict[str, list[Bar]]] = {}
    for era in eras:
        start_dt = datetime(era.start.year, era.start.month, era.start.day, tzinfo=UTC)
        end_dt = datetime(era.end.year, era.end.month, era.end.day, 23, 59, 59, tzinfo=UTC)
        sliced = {
            symbol: [b for b in series if start_dt <= b.ts <= end_dt]
            for symbol, series in bars.items()
        }
        out[era.name] = sliced
    return out


def run_era_splits(
    log: ExperimentLog,
    strategy_name: str,
    params: dict[str, Any],
    bars: dict[str, list[Bar]],
    strategy_factory: Callable[[dict[str, Any]], Strategy],
    costs: CostModel,
    engine_config: EngineConfig,
    bars_per_year: float,
    eras: list[Era] | None = None,
    min_bars: int = 50,
) -> list[EraResult]:
    eras = eras if eras is not None else DEFAULT_ERAS
    sliced = split_by_era(bars, eras)
    results: list[EraResult] = []
    for era in eras:
        era_bars = sliced[era.name]
        lengths = {len(series) for series in era_bars.values()}
        n_bars = min(lengths) if lengths else 0
        if n_bars < min_bars:
            results.append(EraResult(era=era, n_bars=n_bars, result=None))
            continue
        label = f"{strategy_name}/era-{era.name}" + ("-PROVISIONAL" if era.provisional else "")
        result = run_experiment(
            log,
            label,
            {**params, "era": era.name},
            era_bars,
            strategy_factory(params),
            costs,
            engine_config,
            bars_per_year,
        )
        results.append(EraResult(era=era, n_bars=n_bars, result=result))
    return results
