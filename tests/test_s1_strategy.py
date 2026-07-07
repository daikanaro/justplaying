"""S1 TREND_BREAKOUT production-strategy tests on hand-built bars."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

from tests.strategy_helpers import SPECS, hourly_bars, make_instruments, risk_config, s1_params

from qt.backtest.engine import BacktestResult, Engine, EngineConfig, StrategyContext
from qt.backtest.events import Bar
from qt.costs.model import CostModel
from qt.data.events import Event
from qt.strategies.s1_trend_breakout import S1TrendBreakout

CASH = 10_000_000  # $100k

WARMUP = [5000.0, 5001.0, 5000.0, 5001.0, 5000.0]  # fills the 5-bar Donchian window


class StopSpy:
    """Wraps a strategy and records the resting stop level each bar."""

    def __init__(self, inner: S1TrendBreakout, symbol: str) -> None:
        self.inner = inner
        self.symbol = symbol
        self.stop_levels: list[float | None] = []

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        targets = self.inner.on_bar(ctx)
        self.stop_levels.append(ctx.stop_level(self.symbol))
        return targets


def run_s1(closes: list[float], **kwargs: Any) -> tuple[BacktestResult, list[Bar]]:
    events = kwargs.pop("events", None)
    params = kwargs.pop("params", s1_params())
    strategy = S1TrendBreakout(params, risk_config(), SPECS, events)
    bars = {"TST": hourly_bars(closes, **kwargs)}
    costs = CostModel(make_instruments())
    result = Engine(bars, strategy, costs, EngineConfig(CASH)).run()
    return result, bars["TST"]


def test_breakout_entry_fills_next_open_with_capped_size() -> None:
    closes = [*WARMUP, 5010.0, 5010.0, 5010.0]
    result, bars = run_s1(closes)
    entry = result.fills[0]
    assert entry.quantity == 5  # risk formula says more; max_contracts=5 binds
    assert entry.ts == bars[6].ts  # signal at bar 5 close, fill next open
    assert entry.reason == "target"


def test_no_entry_outside_session_window() -> None:
    # Same breakout shape, but bars start 21:30 UTC: the signal bar falls
    # outside 13:30-21:00, and nothing re-triggers afterwards.
    closes = [*WARMUP, 5010.0, 5010.0, 5010.0, 5010.0]
    result, _ = run_s1(closes, start=datetime(2024, 7, 8, 21, 30, tzinfo=UTC))
    assert result.fills == []


def test_event_blackout_blocks_entry() -> None:
    closes = [*WARMUP, 5010.0, 5010.0]
    # The gate is evaluated at the EXECUTION instant — the next bar's open,
    # one bar after the signal close — so the event sits there (bar 6's ts).
    execution_ts = datetime(2024, 7, 8, 14, 0, tzinfo=UTC) + timedelta(hours=6)
    result, _ = run_s1(closes, events=[Event(execution_ts, "FOMC")])
    assert result.fills == []


def test_short_entry_when_allowed_and_blocked_when_not() -> None:
    closes = [*WARMUP, 4990.0, 4990.0, 4990.0]
    result, _bars = run_s1(closes)
    assert result.fills[0].quantity < 0  # short breakout taken
    result_no_short, _ = run_s1(closes, params=s1_params(allow_short=False))
    assert result_no_short.fills == []


def test_opposite_breakout_outside_window_exits_but_does_not_reverse() -> None:
    # Wide bars => big ATR => the trail sits far away and the down-breakout
    # arrives via SIGNAL (bar 7, 21:00 UTC, outside the window), not the stop.
    closes = [*WARMUP, 5010.0, 5010.0, 4993.0, 4993.0, 4993.0]
    result, bars = run_s1(closes, spread=5.0)
    quantities = [f.quantity for f in result.fills]
    # Wide bars -> ATR ~12.6 -> the §1 risk formula (not max_contracts) sizes 3.
    assert quantities == [3, -3]  # exit to flat only — no short outside the window
    assert result.fills[1].reason == "target"
    assert result.fills[1].ts == bars[8].ts  # next-open execution of the exit


def test_trailing_stop_ratchets_up_never_down() -> None:
    closes = [*WARMUP, 5010.0, 5012.0, 5014.0, 5016.0, 5014.0, 5012.0]
    params = s1_params()
    spy = StopSpy(S1TrendBreakout(params, risk_config(), SPECS), "TST")
    bars = {"TST": hourly_bars(closes)}
    Engine(bars, spy, CostModel(make_instruments()), EngineConfig(CASH)).run()
    levels = [lv for lv in spy.stop_levels if lv is not None]
    assert levels, "stop was never set"
    assert all(b >= a for a, b in pairwise(levels))  # ratchet only
    assert levels[-1] > levels[0]  # and it actually ratcheted while price rose


def test_stop_exit_resets_state_for_reentry() -> None:
    # Entry, crash through the stop, then a fresh breakout re-enters.
    # Bars start 09:00 UTC so the whole sequence stays inside the entry window.
    closes = [*WARMUP, 5010.0, 5010.0, 4960.0, 4960.0, 4960.0, 4940.0, 4940.0]
    result, _ = run_s1(closes, start=datetime(2024, 7, 8, 9, 0, tzinfo=UTC))
    reasons = [f.reason for f in result.fills]
    assert "stop" in reasons  # the crash bar trips the trail
    stop_idx = reasons.index("stop")
    assert any(f.quantity < 0 and f.reason == "target" for f in result.fills[stop_idx + 1 :]), (
        "expected a fresh short entry after the stop-out"
    )
