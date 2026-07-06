"""Engine-loop tests: timing, latency, stop management, input validation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qt.backtest.engine import (
    Engine,
    EngineConfig,
    EngineError,
    StopWideningError,
    StrategyContext,
)
from qt.backtest.events import Bar
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel

T0 = datetime(2024, 7, 8, 15, 0, tzinfo=UTC)  # RTH: 1-tick slippage
CASH = 10_000_000


def bars_from_closes(closes: list[float], spread: float = 1.0) -> list[Bar]:
    out = []
    for i, close in enumerate(closes):
        opn = closes[i - 1] if i else close
        out.append(
            Bar(
                ts=T0 + timedelta(hours=i),
                open=opn,
                high=max(opn, close) + spread,
                low=min(opn, close) - spread,
                close=close,
                volume=100.0,
            )
        )
    return out


@pytest.fixture(scope="module")
def costs(config_dir: Path) -> CostModel:
    return CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))


class ScriptedStrategy:
    """Targets (and optional stops) by bar index; None = keep previous target."""

    def __init__(
        self, symbol: str, targets: dict[int, int], stops: dict[int, float] | None = None
    ) -> None:
        self.symbol = symbol
        self.targets = targets
        self.stops = stops or {}
        self._current = 0

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        if ctx.index in self.stops:
            ctx.set_stop(self.symbol, self.stops[ctx.index])
        if ctx.index in self.targets:
            self._current = self.targets[ctx.index]
        return {self.symbol: self._current}


def test_signal_fills_next_bar_open(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0, 5002.0, 5003.0])
    strategy = ScriptedStrategy("MES", {0: 1})
    result = Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()
    (fill,) = result.fills
    assert fill.ts == bars[1].ts  # signal at close 0, fill at bar 1
    assert fill.price == pytest.approx(bars[1].open + 0.25)  # next OPEN + slippage


def test_latency_mode_delays_fill(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0, 5002.0, 5003.0])
    strategy = ScriptedStrategy("MES", {0: 1})
    result = Engine({"MES": bars}, strategy, costs, EngineConfig(CASH, latency_bars=2)).run()
    (fill,) = result.fills
    assert fill.ts == bars[2].ts  # signal at T, fill at T+2


def test_same_bar_fill_is_structurally_impossible() -> None:
    with pytest.raises(EngineError, match="lookahead"):
        EngineConfig(CASH, latency_bars=0)


def test_stop_widening_raises(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0, 5002.0, 5003.0])
    strategy = ScriptedStrategy("MES", {0: 1}, stops={1: 4998.0, 2: 4996.0})  # 2 widens
    with pytest.raises(StopWideningError, match="widens"):
        Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()


def test_stop_ratchet_allowed(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0, 5002.0, 5003.0])
    strategy = ScriptedStrategy("MES", {0: 1}, stops={1: 4998.0, 2: 4999.0})
    result = Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()
    assert len(result.fills) == 1  # entry only; ratcheted stop never hit


def test_stop_without_position_raises(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0])
    strategy = ScriptedStrategy("MES", {}, stops={0: 4998.0})
    with pytest.raises(EngineError, match="no position or pending entry"):
        Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()


def test_reversal_replaces_position_and_stop(costs: CostModel) -> None:
    closes = [5000.0, 5001.0, 5002.0, 5001.0, 5000.0, 4999.0]
    bars = bars_from_closes(closes)
    strategy = ScriptedStrategy("MES", {0: 1, 2: -1}, stops={1: 4995.0})
    result = Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()
    quantities = [f.quantity for f in result.fills]
    assert quantities == [1, -2]  # entry, then flip closes 1 and opens -1
    assert result.signals[2].targets == {"MES": -1}


def test_unknown_symbol_target_raises(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0])
    strategy = ScriptedStrategy("MNQ", {0: 1})
    with pytest.raises(EngineError, match="unknown symbol"):
        Engine({"MES": bars}, strategy, costs, EngineConfig(CASH)).run()


def test_misaligned_symbols_rejected(costs: CostModel) -> None:
    a = bars_from_closes([5000.0, 5001.0])
    b = bars_from_closes([2000.0, 2001.0, 2002.0])
    with pytest.raises(EngineError, match="not aligned"):
        Engine({"MES": a, "M2K": b}, ScriptedStrategy("MES", {}), costs, EngineConfig(CASH))


def test_non_increasing_timestamps_rejected(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0])
    bad = [bars[1], bars[0]]
    with pytest.raises(EngineError, match="strictly increasing"):
        Engine({"MES": bad}, ScriptedStrategy("MES", {}), costs, EngineConfig(CASH))


def test_equity_curve_lengths_match_bars(costs: CostModel) -> None:
    bars = bars_from_closes([5000.0, 5001.0, 5002.0])
    result = Engine({"MES": bars}, ScriptedStrategy("MES", {}), costs, EngineConfig(CASH)).run()
    assert len(result.equity_curve) == 3
    assert result.final_equity_cents == CASH  # never traded
