"""Idempotent order submission with bounded backoff (§4.5 drills c and d).

- Client order ids are deterministic over the order's intent, so a resend of
  the same decision produces the SAME id, and the journal check suppresses it
  (duplicate submit -> no second broker order).
- Placement failures retry with bounded exponential backoff, then give up
  with an alert. There is no unbounded loop anywhere: a forced reject
  produces at most ``max_attempts`` placements and exactly one alert.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum

from qt.oms.alerts import Alerter
from qt.oms.journal import OrderJournal
from qt.oms.state import OrderState


class OrderType(StrEnum):
    MARKET = "market"
    STOP = "stop"


@dataclass(frozen=True)
class OrderIntent:
    """One trading decision. ``decision_id`` names the decision (e.g.
    'S1/MES/2026-07-06T14:00Z/rebalance') — resending the same decision must
    yield the same client_order_id."""

    decision_id: str
    symbol: str
    side: str  # "buy" | "sell"
    quantity: int
    order_type: OrderType = OrderType.MARKET
    stop_price: float | None = None
    # Decision-time price (e.g. the signal close): journaled so the §4.7
    # weekly slippage band can measure fills against it. Deliberately NOT part
    # of the client-order-id hash — the same decision resent with a refreshed
    # mark must still deduplicate.
    reference_price: float | None = None

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            msg = f"side must be buy/sell, got {self.side!r}"
            raise ValueError(msg)
        if self.quantity < 1:
            msg = f"quantity must be >= 1, got {self.quantity}"
            raise ValueError(msg)
        if self.order_type is OrderType.STOP and self.stop_price is None:
            msg = "stop orders require stop_price"
            raise ValueError(msg)

    @property
    def client_order_id(self) -> str:
        payload = "|".join(
            [
                self.decision_id,
                self.symbol,
                self.side,
                str(self.quantity),
                self.order_type.value,
                str(self.stop_price),
            ]
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        return f"QT-{digest}"


class SubmitOutcome(StrEnum):
    PLACED = "placed"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    GAVE_UP = "gave_up"
    # The id is journaled but the order never progressed past PENDING_NEW: a
    # crash hit between record_intent and placement (or between placement and
    # the ACK journal write). Whether it reached the broker is UNKNOWABLE from
    # here — do not silently suppress, do not blindly re-place; reconcile
    # against broker open orders first.
    UNRESOLVED_PENDING = "unresolved_pending"


class PlacementError(Exception):
    """Transient or broker-side placement failure (retryable, bounded)."""


def backoff_delays(base_s: float = 2.0, max_attempts: int = 3) -> Iterator[float]:
    """Exponential: 2, 4, 8, ... — exactly max_attempts entries, then stop."""
    for attempt in range(max_attempts):
        yield base_s * (2**attempt)


class OrderSubmitter:
    def __init__(  # noqa: PLR0913 - explicit wiring, same policy as the harness
        self,
        journal: OrderJournal,
        place: Callable[[OrderIntent, str], None],  # (intent, client_order_id) -> ack or raise
        alerter: Alerter,
        sleep: Callable[[float], None],
        max_attempts: int = 3,
        backoff_base_s: float = 2.0,
    ) -> None:
        if max_attempts < 1:
            msg = f"max_attempts must be >= 1, got {max_attempts}"
            raise ValueError(msg)
        self._journal = journal
        self._place = place
        self._alerter = alerter
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s

    def submit(self, intent: OrderIntent) -> SubmitOutcome:
        order_id = intent.client_order_id
        existing = self._journal.replay().orders.get(order_id)
        if existing is not None:
            if existing.state is OrderState.PENDING_NEW:
                self._alerter.alert(
                    f"order {order_id} ({intent.decision_id}) is journaled but never "
                    "progressed past PENDING_NEW — crash between intent and ack; "
                    "reconcile against broker open orders before acting"
                )
                return SubmitOutcome.UNRESOLVED_PENDING
            self._alerter.alert(f"duplicate submit suppressed: {order_id} ({intent.decision_id})")
            return SubmitOutcome.DUPLICATE_SUPPRESSED
        self._journal.record_intent(
            order_id,
            intent.symbol,
            intent.side,
            intent.quantity,
            intent.order_type.value,
            intent.stop_price,
            intent.reference_price,
        )
        delays = backoff_delays(self._backoff_base_s, self._max_attempts)
        for attempt, delay in enumerate(delays, start=1):
            try:
                self._place(intent, order_id)
            except PlacementError as exc:
                if attempt >= self._max_attempts:
                    self._journal.record_transition(
                        order_id, OrderState.REJECTED, note=f"gave up after {attempt}: {exc}"
                    )
                    self._alerter.alert(f"order {order_id} gave up after {attempt} attempts: {exc}")
                    return SubmitOutcome.GAVE_UP
                self._sleep(delay)
            else:
                self._journal.record_transition(order_id, OrderState.ACKED)
                return SubmitOutcome.PLACED
        msg = "unreachable: backoff loop exhausted without return"  # pragma: no cover
        raise AssertionError(msg)  # pragma: no cover
