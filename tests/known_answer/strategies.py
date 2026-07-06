"""KA-grade S1/S2 logic per BUILD_PLAN §3, used by the known-answer suite.

These are deliberately minimal, incremental (O(1) per bar) implementations of
the strategy RULES — enough to prove engine properties on synthetic data. The
production Strategy classes arrive in slice 4.4; the rules here must match §3:

S1 TREND_BREAKOUT: long when close > Donchian_high(N) (prior N bars,
exclusive); short when close < Donchian_low(N); reversal allowed; k*ATR(m)
trailing stop from best close since entry, ratchets only.

S2 MR_RSI2: long-only; enter when RSI(2) < entry AND (optionally) close >
SMA(200); exit on close > previous high, RSI(2) > exit, or an optional time
stop; optional hard stop 2.5*ATR(14) below entry, never widened.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from qt.backtest.engine import StrategyContext


class WilderAtr:
    """Incremental Wilder ATR (same recurrence as qt.indicators.atr)."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._seed: list[float] = []
        self.value: float | None = None
        self._prev_close: float | None = None

    def update(self, high: float, low: float, close: float) -> float | None:
        tr = (
            high - low
            if self._prev_close is None
            else max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        )
        self._prev_close = close
        if self.value is None:
            self._seed.append(tr)
            if len(self._seed) == self.period:
                self.value = sum(self._seed) / self.period
        else:
            self.value = (self.value * (self.period - 1) + tr) / self.period
        return self.value


class WilderRsi:
    """Incremental Wilder RSI (same recurrence as qt.indicators.rsi)."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._prev_close: float | None = None
        self._changes: list[float] = []
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None
        self.value: float | None = None

    def update(self, close: float) -> float | None:
        if self._prev_close is None:
            self._prev_close = close
            return None
        change = close - self._prev_close
        self._prev_close = close
        if self._avg_gain is None or self._avg_loss is None:
            self._changes.append(change)
            if len(self._changes) == self.period:
                self._avg_gain = sum(max(c, 0.0) for c in self._changes) / self.period
                self._avg_loss = sum(max(-c, 0.0) for c in self._changes) / self.period
            else:
                return None
        else:
            self._avg_gain = (self._avg_gain * (self.period - 1) + max(change, 0.0)) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + max(-change, 0.0)) / self.period
        if self._avg_loss == 0.0:
            self.value = 100.0 if self._avg_gain and self._avg_gain > 0.0 else 50.0
        else:
            self.value = 100.0 - 100.0 / (1.0 + self._avg_gain / self._avg_loss)
        return self.value


@dataclass
class S1KaStrategy:
    """Donchian breakout with k*ATR ratcheting trail, one symbol, ±1 contract."""

    symbol: str
    donchian_n: int = 20
    atr_k: float = 3.0
    atr_period: int = 20
    tick: float = 0.25
    _highs: deque[float] = field(init=False)
    _lows: deque[float] = field(init=False)
    _atr: WilderAtr = field(init=False)
    _best_close: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._highs = deque(maxlen=self.donchian_n)
        self._lows = deque(maxlen=self.donchian_n)
        self._atr = WilderAtr(self.atr_period)

    def _align(self, price: float) -> float:
        return round(price / self.tick) * self.tick

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        bar = ctx.bars(self.symbol)[-1]
        atr = self._atr.update(bar.high, bar.low, bar.close)
        upper = max(self._highs) if len(self._highs) == self.donchian_n else None
        lower = min(self._lows) if len(self._lows) == self.donchian_n else None
        self._highs.append(bar.high)  # appended after: Donchian excludes current bar (§3)
        self._lows.append(bar.low)

        position = ctx.position(self.symbol)
        target = position
        if upper is not None and lower is not None and atr is not None:
            if bar.close > upper and position <= 0:
                target = 1
                self._best_close = bar.close
            elif bar.close < lower and position >= 0:
                target = -1
                self._best_close = bar.close

        if position != 0 and target == position and atr is not None:
            # Ratchet the trail from the best close since entry (§3).
            if position > 0:
                self._best_close = max(self._best_close or bar.close, bar.close)
                proposed = self._align(self._best_close - self.atr_k * atr)
                current = ctx.stop_level(self.symbol)
                if current is None or proposed > current:
                    ctx.set_stop(self.symbol, proposed)
            else:
                self._best_close = min(self._best_close or bar.close, bar.close)
                proposed = self._align(self._best_close + self.atr_k * atr)
                current = ctx.stop_level(self.symbol)
                if current is None or proposed < current:
                    ctx.set_stop(self.symbol, proposed)
        return {self.symbol: target}


@dataclass
class S2KaStrategy:
    """RSI(2) long-only mean reversion with §3 governors, toggleable for KA-3."""

    symbol: str
    trend_filter: bool = True
    hard_stop: bool = True
    time_stop: bool = True
    rsi_entry: float = 10.0
    rsi_exit: float = 65.0
    sma_period: int = 200
    stop_atr_mult: float = 2.5
    atr_period: int = 14
    time_stop_bars: int = 5
    tick: float = 0.10
    _rsi: WilderRsi = field(init=False)
    _atr: WilderAtr = field(init=False)
    _closes_sum: float = field(default=0.0, init=False)
    _closes: deque[float] = field(init=False)
    _prev_high: float | None = field(default=None, init=False)
    _bars_in_trade: int = field(default=0, init=False)
    _entry_pending_since: int | None = field(default=None, init=False)
    _pending_stop_price: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._closes = deque(maxlen=self.sma_period)
        self._rsi = WilderRsi(2)
        self._atr = WilderAtr(self.atr_period)

    def _align(self, price: float) -> float:
        return round(price / self.tick) * self.tick

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        bar = ctx.bars(self.symbol)[-1]
        rsi = self._rsi.update(bar.close)
        atr = self._atr.update(bar.high, bar.low, bar.close)
        if len(self._closes) == self.sma_period:
            self._closes_sum -= self._closes[0]
        self._closes.append(bar.close)
        self._closes_sum += bar.close
        sma = self._closes_sum / self.sma_period if len(self._closes) == self.sma_period else None
        prev_high = self._prev_high
        self._prev_high = bar.high

        position = ctx.position(self.symbol)
        target = position

        if position > 0:
            self._entry_pending_since = None
            if (
                self.hard_stop
                and self._pending_stop_price is not None
                and ctx.stop_level(self.symbol) is None
            ):
                # 2.5*ATR(14) below entry (§3), armed once the position is on;
                # resting from here on and never widened (engine enforces).
                ctx.set_stop(self.symbol, self._pending_stop_price)
            self._bars_in_trade += 1
            exit_now = (prev_high is not None and bar.close > prev_high) or (
                rsi is not None and rsi > self.rsi_exit
            )
            if self.time_stop and self._bars_in_trade >= self.time_stop_bars:
                exit_now = True
            if exit_now:
                target = 0
                self._pending_stop_price = None
        else:
            if self._entry_pending_since is not None and ctx.index > self._entry_pending_since + 1:
                self._entry_pending_since = None  # entry filled and died same bar; re-armable
            if position == 0 and self._entry_pending_since is None:
                self._bars_in_trade = 0
                self._pending_stop_price = None
                warm = rsi is not None and atr is not None and len(self._closes) == self.sma_period
                entry = warm and rsi is not None and rsi < self.rsi_entry
                if entry and self.trend_filter and (sma is None or bar.close <= sma):
                    entry = False
                if entry:
                    target = 1
                    self._entry_pending_since = ctx.index
                    if self.hard_stop and atr is not None:
                        self._pending_stop_price = self._align(bar.close - self.stop_atr_mult * atr)
        return {self.symbol: target}
