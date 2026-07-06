"""Shared dummy strategies and bar builders for validation-harness tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qt.backtest.engine import StrategyContext
from qt.backtest.events import Bar

T0 = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


def trend_bars(
    n: int,
    start: float = 5000.0,
    step: float = 0.5,
    wiggle: float = 2.0,
    tick: float = 0.25,
    start_ts: datetime = T0,
    bar_hours: int = 1,
) -> list[Bar]:
    """Deterministic gently-trending tick-aligned bars (up if step > 0)."""

    def align(price: float) -> float:
        return round(price / tick) * tick

    bars: list[Bar] = []
    prev_close = align(start)
    for i in range(n):
        close = align(start + step * (i + 1) + (wiggle if i % 2 else -wiggle))
        opn = prev_close
        bars.append(
            Bar(
                ts=start_ts + timedelta(hours=i * bar_hours),
                open=opn,
                high=max(opn, close) + tick * 4,
                low=min(opn, close) - tick * 4,
                close=close,
                volume=100.0,
            )
        )
        prev_close = close
    return bars


class HoldStrategy:
    """Always hold ``direction`` contracts of one symbol."""

    def __init__(self, symbol: str, direction: int) -> None:
        self.symbol = symbol
        self.direction = direction

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        return {self.symbol: self.direction}


class FlipStrategy:
    """Alternate long/flat every ``hold`` bars — a reliable round-trip machine."""

    def __init__(self, symbol: str, hold: int = 5) -> None:
        self.symbol = symbol
        self.hold = hold

    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        return {self.symbol: 1 if (ctx.index // self.hold) % 2 == 0 else 0}
