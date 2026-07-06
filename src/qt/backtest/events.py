"""Event types for the engine loop. Timestamps are UTC and must be
non-decreasing through the queue — the engine enforces it (no negative-time
events, §4.2 property)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar; ``ts`` is the bar's start time, UTC, tz-aware."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            msg = f"bar at {self.ts} is timezone-naive"
            raise ValueError(msg)
        if not (
            self.low <= self.open <= self.high
            and self.low <= self.close <= self.high
            and self.low <= self.high
        ):
            msg = f"bar at {self.ts} violates OHLC ordering"
            raise ValueError(msg)


@dataclass(frozen=True)
class MarketEvent:
    ts: datetime
    bars: dict[str, Bar]  # symbol -> bar starting at ts


@dataclass(frozen=True)
class SignalEvent:
    ts: datetime
    targets: dict[str, int]  # symbol -> target contracts (signed)


@dataclass(frozen=True)
class OrderEvent:
    ts: datetime  # when the order becomes executable
    symbol: str
    quantity: int  # signed delta
    reason: str


@dataclass(frozen=True)
class FillEvent:
    ts: datetime
    symbol: str
    quantity: int  # signed
    price: float
    commission_cents: int
    reason: str
