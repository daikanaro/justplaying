"""S2 MR_RSI2 production-strategy tests on hand-built daily bars."""

from datetime import UTC, date, datetime, timedelta

from tests.strategy_helpers import SPECS, daily_bars, make_instruments, risk_config, s2_params

from qt.backtest.engine import Engine, EngineConfig, StrategyContext
from qt.costs.model import CostModel
from qt.data.events import Event
from qt.strategies.s2_mr_rsi2 import S2MeanReversion, next_trading_day

CASH = 10_000_000  # $100k

# Rise (warms the 5-bar SMA), then two down closes (RSI(2) -> 0) that stay
# above the SMA: a textbook S2 entry at index 7.
ENTRY_SETUP = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 109.5, 109.0]


def vix_ok(day: date) -> float | None:
    return 20.0


def run_s2(  # type: ignore[no-untyped-def]
    closes: list[float],
    vix=vix_ok,
    events: list[Event] | None = None,
    cash: int = CASH,
    same_close: bool = False,
):
    strategy = S2MeanReversion(s2_params(), risk_config(), SPECS, vix, events)
    bars = {"TST": daily_bars(closes)}
    costs = CostModel(make_instruments())
    config = EngineConfig(cash, same_close_fills=same_close)
    return Engine(bars, strategy, costs, config).run(), bars["TST"]


def test_entry_fires_next_open_when_all_gates_pass() -> None:
    closes = [*ENTRY_SETUP, 108.75, 108.5]
    result, bars = run_s2(closes)
    entry = result.fills[0]
    assert entry.quantity == 5  # max_contracts caps the risk-formula size
    assert entry.ts == bars[8].ts  # signal at bar 7 close, next-open fill


def test_vix_gate_blocks_entry() -> None:
    closes = [*ENTRY_SETUP, 108.75, 108.5]
    result_high, _ = run_s2(closes, vix=lambda d: 40.0)
    assert result_high.fills == []
    # Missing VIX is fail-safe: gate closed.
    result_none, _ = run_s2(closes, vix=lambda d: None)
    assert result_none.fills == []


def test_calendar_gate_blocks_entry() -> None:
    closes = [*ENTRY_SETUP, 108.75, 108.5]
    signal_day = (datetime(2024, 7, 1, 21, 0, tzinfo=UTC) + timedelta(days=7)).date()
    event = Event(
        datetime.combine(next_trading_day(signal_day), datetime.min.time(), tzinfo=UTC)
        + timedelta(hours=14),
        "CPI",
    )
    result, _ = run_s2(closes, events=[event])
    assert result.fills == []


def test_atr_gate_blocks_entry_on_small_account() -> None:
    closes = [*ENTRY_SETUP, 108.75, 108.5]
    result, _ = run_s2(closes, cash=100_000)  # $1,000: 2.5*ATR risk > 2.5% equity
    assert result.fills == []


def test_exit_on_close_above_previous_high() -> None:
    closes = [*ENTRY_SETUP, 112.0, 112.0, 112.0]
    result, bars = run_s2(closes)
    quantities = [f.quantity for f in result.fills]
    assert quantities == [5, -5]
    assert result.fills[1].ts == bars[9].ts  # exit signal at bar 8, next-open fill


def test_time_stop_exits_after_five_bars() -> None:
    drift = [108.75 - 0.25 * i for i in range(8)]  # keeps RSI low, never above prev high
    closes = [*ENTRY_SETUP, *drift]
    result, bars = run_s2(closes)
    quantities = [f.quantity for f in result.fills]
    assert quantities[:2] == [5, -5]
    # Fill at bar 8; bars_in_trade hits 5 at bar 12; exit fills at bar 13 open.
    assert result.fills[1].ts == bars[13].ts


def test_no_scale_ins_ever() -> None:
    # The down-drift keeps RSI(2) pinned near 0 the whole trade — if scale-ins
    # were possible, the target would grow past the entry size.
    drift = [108.75 - 0.25 * i for i in range(8)]
    closes = [*ENTRY_SETUP, *drift]
    result, _ = run_s2(closes)
    buys = [f for f in result.fills if f.quantity > 0]
    assert len(buys) == 1


def test_hard_stop_set_once_and_never_moved() -> None:
    class StopSpy:
        def __init__(self, inner: S2MeanReversion) -> None:
            self.inner = inner
            self.levels: list[float | None] = []

        def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
            targets = self.inner.on_bar(ctx)
            self.levels.append(ctx.stop_level("TST"))
            return targets

    drift = [108.75 - 0.25 * i for i in range(6)]
    closes = [*ENTRY_SETUP, *drift]
    spy = StopSpy(S2MeanReversion(s2_params(), risk_config(), SPECS, vix_ok))
    Engine(
        {"TST": daily_bars(closes)}, spy, CostModel(make_instruments()), EngineConfig(CASH)
    ).run()
    set_levels = {lv for lv in spy.levels if lv is not None}
    assert len(set_levels) == 1  # set once at entry, never widened, never tightened


def test_same_close_mode_fills_on_signal_bar() -> None:
    closes = [*ENTRY_SETUP, 108.75, 108.5]
    next_open, bars = run_s2(closes)
    same_close, _ = run_s2(closes, same_close=True)
    assert next_open.fills[0].ts == bars[8].ts  # next-open mode: fill next bar
    assert same_close.fills[0].ts == bars[7].ts  # same-close mode: signal bar
    assert same_close.fills[0].reason == "target-same-close"


def test_next_trading_day_skips_weekend() -> None:
    assert next_trading_day(date(2024, 7, 5)) == date(2024, 7, 8)  # Fri -> Mon
    assert next_trading_day(date(2024, 7, 8)) == date(2024, 7, 9)
