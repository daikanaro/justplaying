"""Order types understood by the execution simulator.

Strategies never construct these (§3: strategies emit target positions);
the engine and the known-answer/property tests do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from itertools import count

_order_ids = count(1)


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


@dataclass
class _OrderBase:
    symbol: str
    side: Side
    quantity: int  # always positive; direction lives in ``side``
    order_id: int = field(default_factory=lambda: next(_order_ids), kw_only=True)
    filled: int = field(default=0, kw_only=True)  # contracts filled so far

    def __post_init__(self) -> None:
        if self.quantity < 1:
            msg = f"order quantity must be >= 1, got {self.quantity}"
            raise ValueError(msg)

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled


@dataclass
class MarketOrder(_OrderBase):
    """Fills at bar open ± session-aware slippage."""


@dataclass
class StopOrder(_OrderBase):
    """Protective stop. SELL stop guards longs (triggers at/below stop);
    BUY stop guards shorts. Gap-through is modeled: if the bar opens beyond
    the stop, the fill is at the open, not the stop (§4, mandatory)."""

    stop_price: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.stop_price <= 0.0:
            msg = f"stop_price must be > 0, got {self.stop_price}"
            raise ValueError(msg)


@dataclass
class LimitOrder(_OrderBase):
    """Fills only if price trades THROUGH the limit by >= 1 tick (conservative
    queue heuristic, §4); fill price is the limit (or better at the open)."""

    limit_price: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.limit_price <= 0.0:
            msg = f"limit_price must be > 0, got {self.limit_price}"
            raise ValueError(msg)


Order = MarketOrder | StopOrder | LimitOrder
