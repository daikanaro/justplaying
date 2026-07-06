"""Native (broker-resting) stop management: create and ratchet; widening is
structurally impossible — same invariant as the backtest engine, enforced
here for the live path (§3, §4.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class StopSide(StrEnum):
    SELL = "sell"  # protects a long: ratchet means the price only goes UP
    BUY = "buy"  # protects a short: ratchet means the price only goes DOWN


class StopWideningError(Exception):
    """Attempted to move a protective stop AWAY from the market."""


@dataclass(frozen=True)
class NativeStop:
    symbol: str
    side: StopSide
    quantity: int
    price: float
    broker_order_id: str


class NativeStopManager:
    """Owns one resting stop per symbol. ``place`` submits a new stop and
    returns the broker order id; ``modify`` moves an existing one."""

    def __init__(
        self,
        place: Callable[[str, StopSide, int, float], str],
        modify: Callable[[str, float, int], None],  # (broker_order_id, price, quantity)
        cancel: Callable[[str], None],
    ) -> None:
        self._place = place
        self._modify = modify
        self._cancel = cancel
        self._stops: dict[str, NativeStop] = {}

    def current(self, symbol: str) -> NativeStop | None:
        return self._stops.get(symbol)

    def upsert(self, symbol: str, side: StopSide, quantity: int, price: float) -> NativeStop:
        """Create the stop, or ratchet/resize it. Raises on any widening."""
        if quantity < 1 or price <= 0.0:
            msg = f"{symbol}: stop needs quantity >= 1 and price > 0"
            raise ValueError(msg)
        existing = self._stops.get(symbol)
        if existing is None or existing.side is not side:
            if existing is not None:  # position flipped: the old stop is void
                self._cancel(existing.broker_order_id)
            broker_id = self._place(symbol, side, quantity, price)
            stop = NativeStop(symbol, side, quantity, price, broker_id)
        else:
            widening = (side is StopSide.SELL and price < existing.price) or (
                side is StopSide.BUY and price > existing.price
            )
            if widening:
                msg = (
                    f"{symbol}: stop {existing.price} -> {price} widens the stop; "
                    "ratchets only (§3)"
                )
                raise StopWideningError(msg)
            if price == existing.price and quantity == existing.quantity:
                return existing  # nothing to do; no broker chatter
            self._modify(existing.broker_order_id, price, quantity)
            stop = NativeStop(symbol, side, quantity, price, existing.broker_order_id)
        self._stops[symbol] = stop
        return stop

    def release(self, symbol: str) -> None:
        """Position closed: cancel and forget the resting stop."""
        existing = self._stops.pop(symbol, None)
        if existing is not None:
            self._cancel(existing.broker_order_id)
