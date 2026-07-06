"""Hand-rolled indicators per BUILD_PLAN §3 definitions, needed by the
known-answer suite (slice 4.2) and the strategies (slice 4.4).

Definitions (locked): EMA standard recursive; ATR = Wilder smoothing of true
range; RSI = Wilder; Donchian(N) = rolling max/min of the PRIOR N bars
(exclusive of the current bar); SMA plain arithmetic.

All functions take plain float sequences and return lists aligned to the
input, with None where the indicator is not yet defined — an undefined
indicator must never silently read as 0.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> list[float | None]:
    _require_period(period)
    out: list[float | None] = [None] * len(values)
    window_sum = 0.0
    for i, v in enumerate(values):
        window_sum += v
        if i >= period:
            window_sum -= values[i - period]
        if i >= period - 1:
            out[i] = window_sum / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Standard recursive EMA, seeded with the SMA of the first ``period`` values."""
    _require_period(period)
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = current + alpha * (values[i] - current)
        out[i] = current
    return out


def true_range(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> list[float]:
    """TR_0 = high - low; thereafter max(h-l, |h-prev_c|, |l-prev_c|)."""
    _require_same_length(highs, lows, closes)
    out: list[float] = []
    for i in range(len(highs)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            prev_close = closes[i - 1]
            out.append(
                max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close))
            )
    return out


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int
) -> list[float | None]:
    """Wilder ATR: seed = mean of first ``period`` TRs, then
    ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period."""
    _require_period(period)
    trs = true_range(highs, lows, closes)
    out: list[float | None] = [None] * len(trs)
    if len(trs) < period:
        return out
    current = sum(trs[:period]) / period
    out[period - 1] = current
    for i in range(period, len(trs)):
        current = (current * (period - 1) + trs[i]) / period
        out[i] = current
    return out


def rsi(closes: Sequence[float], period: int) -> list[float | None]:
    """Wilder RSI: seed averages over the first ``period`` changes, then Wilder
    smoothing. All-gain windows read 100; all-loss windows read 0."""
    _require_period(period)
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def donchian_high(highs: Sequence[float], period: int) -> list[float | None]:
    """Rolling max of the PRIOR ``period`` highs, exclusive of the current bar (§3)."""
    return _donchian(highs, period, is_high=True)


def donchian_low(lows: Sequence[float], period: int) -> list[float | None]:
    """Rolling min of the PRIOR ``period`` lows, exclusive of the current bar (§3)."""
    return _donchian(lows, period, is_high=False)


def _donchian(values: Sequence[float], period: int, is_high: bool) -> list[float | None]:
    _require_period(period)
    out: list[float | None] = [None] * len(values)
    window: deque[float] = deque(maxlen=period)
    for i, v in enumerate(values):
        if len(window) == period:
            out[i] = max(window) if is_high else min(window)
        window.append(v)  # appended AFTER: bar i never sees itself
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0  # flat window: neutral, not overbought
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _require_period(period: int) -> None:
    if period < 1:
        msg = f"period must be >= 1, got {period}"
        raise ValueError(msg)


def _require_same_length(*seqs: Sequence[float]) -> None:
    lengths = {len(s) for s in seqs}
    if len(lengths) != 1:
        msg = f"sequences must share a length, got {sorted(lengths)}"
        raise ValueError(msg)
