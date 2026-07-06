"""S2 MR_RSI2 (BUILD_PLAN §3), config-driven, long-only, no scale-ins.

Entry (long only in v1), ALL gates must pass on the signal bar's close:
- RSI(2) < entry threshold,
- close > SMA(200) trend filter,
- ATR gate: k_stop * ATR(14) * $/point <= mr_atr_gate_equity_pct * equity,
- VIX < vix_max_for_mr (missing VIX = gate closed, fail-safe),
- no calendar event during the NEXT session (trading day).

Exit, whichever first (next-open execution): close > previous bar's high, or
RSI(2) > exit threshold, or the time stop. Hard stop 2.5*ATR(14) below entry,
resting at the broker, never widened — a model-falsification line, so it is
set once at entry and only the engine's never-widen API touches it.

Scale-ins were deliberately removed (tail multiplier) — a filled position
never increases.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import sqrt

from qt.backtest.engine import StrategyContext
from qt.config.schemas import MrRsi2Config, RiskConfig
from qt.data.events import Event
from qt.strategies.sizing import size_position

VixProvider = Callable[[date], float | None]

_SATURDAY = 5


def next_trading_day(day: date) -> date:
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= _SATURDAY:
        nxt += timedelta(days=1)
    return nxt


@dataclass
class _SymbolState:
    closes: deque[float]
    closes_sum: float = 0.0
    prev_close: float | None = None
    prev_high: float | None = None
    atr: float | None = None
    atr_seed: list[float] = field(default_factory=list)
    rsi_avg_gain: float | None = None
    rsi_avg_loss: float | None = None
    rsi_changes: list[float] = field(default_factory=list)
    rsi: float | None = None
    bars_in_trade: int = 0
    entry_pending_since: int | None = None
    pending_stop: float | None = None


class S2MeanReversion:
    def __init__(
        self,
        params: MrRsi2Config,
        risk: RiskConfig,
        instrument_specs: dict[str, tuple[float, float]],  # symbol -> ($/point, tick)
        vix: VixProvider,
        events: list[Event] | None = None,
    ) -> None:
        self._params = params
        self._risk = risk
        self._specs = instrument_specs
        self._vix = vix
        self._events = events or []
        missing = [s for s in params.symbols if s not in instrument_specs]
        if missing:
            msg = f"S2 missing instrument specs for {missing}"
            raise ValueError(msg)
        self._state = {
            s: _SymbolState(closes=deque(maxlen=params.sma_filter_period)) for s in params.symbols
        }

    # -- indicator upkeep ---------------------------------------------------

    def _update(self, state: _SymbolState, high: float, low: float, close: float) -> None:
        period = self._params.rsi_period
        if state.prev_close is not None:
            change = close - state.prev_close
            if state.rsi_avg_gain is None or state.rsi_avg_loss is None:
                state.rsi_changes.append(change)
                if len(state.rsi_changes) == period:
                    state.rsi_avg_gain = sum(max(c, 0.0) for c in state.rsi_changes) / period
                    state.rsi_avg_loss = sum(max(-c, 0.0) for c in state.rsi_changes) / period
            else:
                state.rsi_avg_gain = (state.rsi_avg_gain * (period - 1) + max(change, 0.0)) / period
                state.rsi_avg_loss = (
                    state.rsi_avg_loss * (period - 1) + max(-change, 0.0)
                ) / period
            if state.rsi_avg_gain is not None and state.rsi_avg_loss is not None:
                if state.rsi_avg_loss == 0.0:
                    state.rsi = 100.0 if state.rsi_avg_gain > 0.0 else 50.0
                else:
                    state.rsi = 100.0 - 100.0 / (1.0 + state.rsi_avg_gain / state.rsi_avg_loss)
        tr = (
            high - low
            if state.prev_close is None
            else max(high - low, abs(high - state.prev_close), abs(low - state.prev_close))
        )
        atr_period = self._params.hard_stop_atr_period
        if state.atr is None:
            state.atr_seed.append(tr)
            if len(state.atr_seed) == atr_period:
                state.atr = sum(state.atr_seed) / atr_period
        else:
            state.atr = (state.atr * (atr_period - 1) + tr) / atr_period
        if len(state.closes) == self._params.sma_filter_period:
            state.closes_sum -= state.closes[0]
        state.closes.append(close)
        state.closes_sum += close
        state.prev_close = close

    def _sma(self, state: _SymbolState) -> float | None:
        if len(state.closes) < self._params.sma_filter_period:
            return None
        return state.closes_sum / self._params.sma_filter_period

    # -- gates ----------------------------------------------------------------

    def _atr_gate_open(self, ctx: StrategyContext, symbol: str, atr: float) -> bool:
        dollars_per_point, _ = self._specs[symbol]
        stop_risk_cents = self._params.hard_stop_atr_mult * atr * dollars_per_point * 100.0
        return stop_risk_cents <= self._risk.mr_atr_gate_equity_pct * ctx.equity_cents

    def _vix_gate_open(self, day: date) -> bool:
        value = self._vix(day)
        return value is not None and value < self._risk.vix_max_for_mr

    def _calendar_clear(self, day: date) -> bool:
        nxt = next_trading_day(day)
        return not any(e.ts_utc.date() == nxt for e in self._events)

    # -- main -------------------------------------------------------------------

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        targets: dict[str, int] = {}
        for symbol in self._params.symbols:
            bar = ctx.bars(symbol)[-1]
            state = self._state[symbol]
            prev_high = state.prev_high
            self._update(state, bar.high, bar.low, bar.close)
            state.prev_high = bar.high
            position = ctx.position(symbol)
            target = position  # scale-ins impossible: target never exceeds position

            if position > 0:
                state.entry_pending_since = None
                if state.pending_stop is not None and ctx.stop_level(symbol) is None:
                    ctx.set_stop(symbol, state.pending_stop)  # resting; never widened
                    state.pending_stop = None
                state.bars_in_trade += 1
                exit_now = (prev_high is not None and bar.close > prev_high) or (
                    state.rsi is not None and state.rsi > self._params.rsi_exit_above
                )
                if state.bars_in_trade >= self._params.time_stop_bars:
                    exit_now = True
                if exit_now:
                    target = 0
                    state.pending_stop = None
            else:
                if state.entry_pending_since is not None and (
                    ctx.index > state.entry_pending_since + 1
                ):
                    state.entry_pending_since = None
                if position == 0 and state.entry_pending_since is None:
                    state.bars_in_trade = 0
                    sma = self._sma(state)
                    day = bar.ts.date()
                    warm = state.rsi is not None and state.atr is not None and sma is not None
                    entry = (
                        warm
                        and state.rsi is not None
                        and state.rsi < self._params.rsi_entry_below
                        and sma is not None
                        and bar.close > sma
                        and state.atr is not None
                        and self._atr_gate_open(ctx, symbol, state.atr)
                        and self._vix_gate_open(day)
                        and self._calendar_clear(day)
                    )
                    if entry and state.atr is not None:
                        dollars_per_point, tick = self._specs[symbol]
                        size = size_position(
                            equity_cents=ctx.equity_cents,
                            risk_fraction=self._risk.per_trade_risk_default,
                            stop_points=self._params.hard_stop_atr_mult * state.atr,
                            dollars_per_point=dollars_per_point,
                            daily_dollar_vol_per_contract=state.atr * sqrt(1.0) * dollars_per_point,
                            max_contracts=self._risk.max_contracts.get(symbol, 0),
                        )
                        if size > 0:
                            target = size
                            state.entry_pending_since = ctx.index
                            stop_raw = bar.close - self._params.hard_stop_atr_mult * state.atr
                            state.pending_stop = round(stop_raw / tick) * tick
            targets[symbol] = target
        return targets
