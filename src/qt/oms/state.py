"""Order state machine (§4.5): PENDING_NEW, ACKED, PARTIAL, FILLED,
CANCELLED, REJECTED, UNKNOWN.

The transition table is the single source of truth; OrderRecord.transition
raises on anything not in it. Practical notes baked into the table:
- fills can arrive before the ack (IBKR does this), so PENDING_NEW may jump
  straight to PARTIAL/FILLED;
- UNKNOWN is the reconnect state: it may resolve to any concrete state;
- FILLED / CANCELLED / REJECTED are absorbing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class OrderState(StrEnum):
    PENDING_NEW = "PENDING_NEW"
    ACKED = "ACKED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


LEGAL_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.PENDING_NEW: frozenset(
        {
            OrderState.ACKED,
            OrderState.PARTIAL,
            OrderState.FILLED,
            OrderState.REJECTED,
            OrderState.CANCELLED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.ACKED: frozenset(
        {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELLED, OrderState.UNKNOWN}
    ),
    OrderState.PARTIAL: frozenset(
        {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELLED, OrderState.UNKNOWN}
    ),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.UNKNOWN: frozenset(
        {
            OrderState.ACKED,
            OrderState.PARTIAL,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
        }
    ),
}

TERMINAL_STATES = frozenset({OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED})


class IllegalTransitionError(Exception):
    """The broker/journal reported a transition the state machine forbids."""


@dataclass
class OrderRecord:
    """One order's lifecycle. Quantity is unsigned; direction lives upstream."""

    client_order_id: str
    symbol: str
    quantity: int
    state: OrderState = OrderState.PENDING_NEW
    filled_quantity: int = 0
    history: list[OrderState] = field(default_factory=lambda: [OrderState.PENDING_NEW])

    def __post_init__(self) -> None:
        if self.quantity < 1:
            msg = f"{self.client_order_id}: order quantity must be >= 1"
            raise IllegalTransitionError(msg)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled_quantity

    def transition(self, new_state: OrderState, fill_quantity: int = 0) -> None:
        """Apply one lifecycle event. ``fill_quantity`` is the increment
        carried by PARTIAL/FILLED events (0 elsewhere)."""
        if new_state not in LEGAL_TRANSITIONS[self.state]:
            msg = (
                f"{self.client_order_id}: illegal transition "
                f"{self.state.value} -> {new_state.value}"
            )
            raise IllegalTransitionError(msg)
        if fill_quantity < 0:
            msg = f"{self.client_order_id}: negative fill quantity {fill_quantity}"
            raise IllegalTransitionError(msg)
        if fill_quantity and new_state not in (OrderState.PARTIAL, OrderState.FILLED):
            msg = f"{self.client_order_id}: {new_state.value} cannot carry a fill"
            raise IllegalTransitionError(msg)
        new_filled = self.filled_quantity + fill_quantity
        if new_state is OrderState.PARTIAL:
            if fill_quantity == 0 and self.state is not OrderState.UNKNOWN:
                msg = f"{self.client_order_id}: PARTIAL requires a fill increment"
                raise IllegalTransitionError(msg)
            if new_filled >= self.quantity:
                msg = (
                    f"{self.client_order_id}: PARTIAL with cumulative {new_filled} >= "
                    f"order quantity {self.quantity} (should be FILLED)"
                )
                raise IllegalTransitionError(msg)
        if new_state is OrderState.FILLED and new_filled != self.quantity:
            msg = (
                f"{self.client_order_id}: FILLED with cumulative {new_filled} != "
                f"order quantity {self.quantity}"
            )
            raise IllegalTransitionError(msg)
        if new_filled > self.quantity:
            msg = f"{self.client_order_id}: overfill {new_filled} > {self.quantity}"
            raise IllegalTransitionError(msg)
        self.filled_quantity = new_filled
        self.state = new_state
        self.history.append(new_state)
