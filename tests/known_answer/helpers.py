"""Shared helpers for the known-answer suite: synthetic worlds and
round-trip extraction from fill streams."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from qt.backtest.events import Bar, FillEvent

T0 = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)


def align(price: float, tick: float) -> float:
    return round(price / tick) * tick


def gbm_bars(
    seed: int,
    n: int,
    s0: float = 5000.0,
    sigma_per_bar: float = 0.002,
    tick: float = 0.25,
    bar_hours: int = 1,
) -> list[Bar]:
    """Driftless GBM (mu = 0 -> log-drift -sigma^2/2), tick-aligned OHLC bars.
    No autocorrelation by construction: any measured edge is an engine bug."""
    rng = random.Random(seed)
    bars: list[Bar] = []
    level = s0
    prev_close = align(s0, tick)
    for i in range(n):
        level *= math.exp(rng.gauss(-0.5 * sigma_per_bar**2, sigma_per_bar))
        close = align(max(level, 100.0), tick)
        opn = prev_close
        high = max(opn, close) + tick * rng.randint(0, 4)
        low = min(opn, close) - tick * rng.randint(0, 4)
        bars.append(
            Bar(
                ts=T0 + timedelta(hours=i * bar_hours),
                open=opn,
                high=high,
                low=low,
                close=close,
                volume=1000.0,
            )
        )
        prev_close = close
    return bars


def round_trips(fills: list[FillEvent], tick: float, tick_value_cents: int) -> list[int]:
    """Net cents per flat-to-flat round trip for a +/-1-position strategy.

    Handles reversals (a single +/-2 fill closes one trade and opens the next
    at the same price). Commissions are taken from the fills themselves.
    An open position at the end of the stream is ignored (no exit, no trade).
    """
    trades: list[int] = []
    position = 0
    entry_ticks = 0
    open_pnl_cents = 0

    for fill in fills:
        price_ticks = round(fill.price / tick)
        quantity = fill.quantity
        per_contract_commission = fill.commission_cents // abs(quantity)
        while quantity != 0:
            if position == 0:  # opening
                step = quantity
                position = step
                entry_ticks = price_ticks
                open_pnl_cents = -per_contract_commission * abs(step)
                quantity = 0
            elif (position > 0) != (quantity > 0):  # closing (possibly into a flip)
                closed = min(abs(position), abs(quantity))
                direction = 1 if position > 0 else -1
                pnl = (price_ticks - entry_ticks) * tick_value_cents * direction * closed
                open_pnl_cents += pnl - per_contract_commission * closed
                position -= direction * closed
                quantity += direction * closed
                if position == 0:
                    trades.append(open_pnl_cents)
                    open_pnl_cents = 0
            else:  # adding (not used by +/-1 strategies, but stay correct)
                position += quantity
                open_pnl_cents -= per_contract_commission * abs(quantity)
                quantity = 0
    return trades


def mean_stderr(values: list[int]) -> tuple[float, float]:
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, float("inf")
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var / n)
