"""S1 TREND_BREAKOUT (BUILD_PLAN §3), config-driven, multi-symbol.

Rules (locked):
- Long when close > Donchian_high(N) of the PRIOR N bars; short when close <
  Donchian_low(N). Reversal allowed.
- Initial & trailing stop k*ATR(m) from the best close since entry; ratchets
  on favorable closes only; widening is impossible (engine API).
- Exit: trail hit (resting stop, active 24h) or opposite signal.
- Entries only inside the configured UTC session window and outside the
  event-blackout window; exits are never restricted.

Interpretation note (documented, not spec'd): an opposite breakout OUTSIDE the
entry window exits to flat (an exit is allowed 24h) but does NOT open the
reverse position — the new entry waits for a signal inside the window.

Timing note: signals are computed at a bar's CLOSE and fill at the NEXT bar's
open (engine latency_bars=1 — this strategy assumes exactly that). The entry
window / blackout gates are therefore evaluated at the fill instant
(bar start + bar duration), not at the signal bar's start: gating on the
bar-start time would let a 13:59 signal trade at 14:00 through a window that
closed at 14:00.

Sizing per §1 via qt.strategies.sizing; the daily $vol input for the
vol-target overlay is estimated as bar-ATR * sqrt(bars_per_day) * $/point.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from math import sqrt

from qt.backtest.engine import StrategyContext
from qt.config.schemas import RiskConfig, TrendBreakoutParams
from qt.data.events import Event, in_blackout
from qt.strategies.sizing import size_position

_BARS_PER_DAY = {"1h": 23.0, "1d": 1.0}  # Globex trades ~23h/day
_BAR_DURATION = {"1h": timedelta(hours=1), "1d": timedelta(days=1)}


@dataclass
class _SymbolState:
    highs: deque[float]
    lows: deque[float]
    atr: float | None = None
    atr_seed: list[float] = field(default_factory=list)
    prev_close: float | None = None
    best_close: float | None = None
    entry_pending_since: int | None = None


class S1TrendBreakout:
    def __init__(
        self,
        params: TrendBreakoutParams,
        risk: RiskConfig,
        instrument_specs: dict[str, tuple[float, float]],  # symbol -> ($/point, tick)
        events: list[Event] | None = None,
    ) -> None:
        self._params = params
        self._risk = risk
        self._specs = instrument_specs
        self._events = events or []
        missing = [s for s in params.symbols if s not in instrument_specs]
        if missing:
            msg = f"S1 missing instrument specs for {missing}"
            raise ValueError(msg)
        self._state = {
            s: _SymbolState(
                highs=deque(maxlen=params.donchian_n), lows=deque(maxlen=params.donchian_n)
            )
            for s in params.symbols
        }
        self._bars_per_day = _BARS_PER_DAY[params.bar_timeframe]
        self._bar_duration = _BAR_DURATION[params.bar_timeframe]

    # -- gates ------------------------------------------------------------

    def _in_entry_window(self, ts_utc: datetime) -> bool:
        window = self._params.entry_session_utc
        if window is None:
            return True  # TF-D: no intraday window
        start_h, start_m = (int(x) for x in window.start.split(":"))
        end_h, end_m = (int(x) for x in window.end.split(":"))
        start, end = time(start_h, start_m), time(end_h, end_m)
        now = ts_utc.time()
        if start < end:
            return start <= now < end
        return now >= start or now < end  # overnight window

    def _entry_allowed(self, ts_utc: datetime) -> bool:
        return self._in_entry_window(ts_utc) and not in_blackout(
            ts_utc, self._events, self._risk.event_blackout_min
        )

    # -- indicator upkeep ---------------------------------------------------

    def _update_indicators(
        self, state: _SymbolState, high: float, low: float, close: float
    ) -> tuple[float | None, float | None]:
        """Returns (donchian_high, donchian_low) of the PRIOR N bars, then
        pushes the current bar; updates Wilder ATR."""
        n = self._params.donchian_n
        upper = max(state.highs) if len(state.highs) == n else None
        lower = min(state.lows) if len(state.lows) == n else None
        tr = (
            high - low
            if state.prev_close is None
            else max(high - low, abs(high - state.prev_close), abs(low - state.prev_close))
        )
        period = self._params.atr_period
        if state.atr is None:
            state.atr_seed.append(tr)
            if len(state.atr_seed) == period:
                state.atr = sum(state.atr_seed) / period
        else:
            state.atr = (state.atr * (period - 1) + tr) / period
        state.prev_close = close
        state.highs.append(high)
        state.lows.append(low)
        return upper, lower

    # -- sizing & stops -----------------------------------------------------

    def _entry_size(self, ctx: StrategyContext, symbol: str, atr: float) -> int:
        dollars_per_point, _tick = self._specs[symbol]
        return size_position(
            equity_cents=ctx.equity_cents,
            risk_fraction=self._risk.per_trade_risk_default,
            stop_points=self._params.atr_stop_k * atr,
            dollars_per_point=dollars_per_point,
            daily_dollar_vol_per_contract=atr * sqrt(self._bars_per_day) * dollars_per_point,
            max_contracts=self._risk.max_contracts.get(symbol, 0),
        )

    def _align(self, symbol: str, price: float) -> float:
        tick = self._specs[symbol][1]
        return round(price / tick) * tick

    def _trail(self, ctx: StrategyContext, symbol: str, state: _SymbolState, close: float) -> None:
        """§3: the trail ratchets on FAVORABLE CLOSES only. A bar that does not
        improve best_close never moves the stop — otherwise ATR contraction
        alone would tighten it, which is a different (unspecified) exit rule."""
        atr = state.atr
        if atr is None:
            return
        position = ctx.position(symbol)
        current = ctx.stop_level(symbol)
        if position > 0:
            improved = state.best_close is None or close > state.best_close
            state.best_close = max(state.best_close or close, close)
            if current is not None and not improved:
                return
            proposed = self._align(symbol, state.best_close - self._params.atr_stop_k * atr)
            if current is None or proposed > current:
                ctx.set_stop(symbol, proposed)
        elif position < 0:
            improved = state.best_close is None or close < state.best_close
            state.best_close = min(state.best_close or close, close)
            if current is not None and not improved:
                return
            proposed = self._align(symbol, state.best_close + self._params.atr_stop_k * atr)
            if current is None or proposed < current:
                ctx.set_stop(symbol, proposed)

    # -- main ---------------------------------------------------------------

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:  # noqa: PLR0912 - the §3 rule tree, kept in one visible place
        targets: dict[str, int] = {}
        for symbol in self._params.symbols:
            bar = ctx.bars(symbol)[-1]
            state = self._state[symbol]
            upper, lower = self._update_indicators(state, bar.high, bar.low, bar.close)
            position = ctx.position(symbol)
            target = position

            if position == 0 and state.entry_pending_since is not None:
                if ctx.index > state.entry_pending_since + 1:
                    state.entry_pending_since = None  # order resolved and died; re-armable
            elif position != 0:
                state.entry_pending_since = None

            warm = upper is not None and lower is not None and state.atr is not None
            breakout_up = warm and upper is not None and bar.close > upper
            breakout_down = warm and lower is not None and bar.close < lower
            # Gate at the EXECUTION instant: the fill happens at the next
            # bar's open (= this bar's start + duration; latency_bars=1).
            entry_ok = self._entry_allowed(bar.ts + self._bar_duration)

            if position == 0 and state.entry_pending_since is None:
                state.best_close = None
                if warm and entry_ok and state.atr is not None:
                    if breakout_up:
                        target = self._entry_size(ctx, symbol, state.atr)
                    elif breakout_down and self._params.allow_short:
                        target = -self._entry_size(ctx, symbol, state.atr)
                    if target != 0:
                        state.entry_pending_since = ctx.index
                        state.best_close = bar.close
            elif position > 0 and breakout_down:
                if entry_ok and self._params.allow_short and state.atr is not None:
                    target = -self._entry_size(ctx, symbol, state.atr)  # reversal
                    state.best_close = bar.close
                    state.entry_pending_since = ctx.index
                else:
                    target = 0  # exit is allowed 24h; the new short is not
                    state.best_close = None
            elif position < 0 and breakout_up:
                if entry_ok and state.atr is not None:
                    target = self._entry_size(ctx, symbol, state.atr)
                    state.best_close = bar.close
                    state.entry_pending_since = ctx.index
                else:
                    target = 0
                    state.best_close = None
            elif position != 0:
                self._trail(ctx, symbol, state, bar.close)

            targets[symbol] = target
        return targets
