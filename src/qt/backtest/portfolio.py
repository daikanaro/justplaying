"""Cent-exact portfolio accounting with the §4 invariant.

Money is integer cents and prices are integer tick counts throughout — every
P&L number is exact by construction (FIFO lots, no floating averages). The
invariant — cash + Σ(position marks) == equity — is verified on every event:
``equity_cents`` is maintained incrementally (a delta per fill/mark/accrual),
while ``recompute_equity`` derives it fresh from cash and open lots. Any
divergence raises AccountingError immediately; a backtest that cannot account
for itself to the cent must die, not report numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from qt.backtest.events import FillEvent
from qt.costs.model import CostModel


class AccountingError(Exception):
    """The two equity computations diverged (or an impossible state arose)."""


@dataclass
class Lot:
    quantity: int  # signed; all lots in one position share a sign
    entry_ticks: int


@dataclass
class Position:
    lots: list[Lot] = field(default_factory=list)
    mark_ticks: int = 0

    @property
    def quantity(self) -> int:
        return sum(lot.quantity for lot in self.lots)


class Portfolio:
    def __init__(self, costs: CostModel, initial_cash_cents: int) -> None:
        if initial_cash_cents <= 0:
            msg = f"initial cash must be positive, got {initial_cash_cents}"
            raise ValueError(msg)
        self._costs = costs
        self.cash_cents = initial_cash_cents
        self.equity_cents = initial_cash_cents  # incrementally maintained
        self.positions: dict[str, Position] = {}
        self.margin_breaches: list[datetime] = []

    # -- fills ----------------------------------------------------------

    def apply_fill(self, fill: FillEvent) -> None:
        if fill.quantity == 0:
            msg = f"zero-quantity fill at {fill.ts}"
            raise AccountingError(msg)
        position = self.positions.setdefault(fill.symbol, Position())
        fill_ticks = self._costs.price_to_ticks(fill.symbol, fill.price)
        tick_value = self._costs.spec(fill.symbol).tick_value_cents

        before_unrealized = self._unrealized_cents(fill.symbol, position)
        realized = 0
        remaining = fill.quantity
        # Closing leg: consume FIFO lots while the fill opposes the position.
        while remaining != 0 and position.lots and (position.lots[0].quantity * remaining) < 0:
            lot = position.lots[0]
            closed = min(abs(remaining), abs(lot.quantity))
            direction = 1 if lot.quantity > 0 else -1
            realized += (fill_ticks - lot.entry_ticks) * tick_value * direction * closed
            lot.quantity -= direction * closed
            remaining += direction * closed
            if lot.quantity == 0:
                position.lots.pop(0)
        # Opening leg (fresh, add, or the far side of a flip).
        if remaining != 0:
            position.lots.append(Lot(remaining, fill_ticks))

        position.mark_ticks = fill_ticks
        self.cash_cents += realized - fill.commission_cents
        after_unrealized = self._unrealized_cents(fill.symbol, position)
        self.equity_cents += (
            realized - fill.commission_cents + (after_unrealized - before_unrealized)
        )
        self.check_invariant(fill.ts)

    # -- marks ----------------------------------------------------------

    def mark_to_market(self, ts: datetime, marks: dict[str, float]) -> None:
        delta = 0
        for symbol, price in marks.items():
            position = self.positions.get(symbol)
            if position is None:
                continue
            before = self._unrealized_cents(symbol, position)
            position.mark_ticks = self._costs.price_to_ticks(symbol, price)
            delta += self._unrealized_cents(symbol, position) - before
        self.equity_cents += delta
        self.check_invariant(ts)

    # -- funding hook (present but inert for venue 1, §4) -----------------

    def accrue_funding(self, ts: datetime) -> None:
        for symbol, position in self.positions.items():
            if position.quantity != 0:
                accrual = self._costs.funding_accrual_cents(symbol, ts)
                if accrual:  # pragma: no cover - venue 2 wires this
                    self.cash_cents += accrual
                    self.equity_cents += accrual
        self.check_invariant(ts)

    # -- invariants & views ----------------------------------------------

    def recompute_equity(self) -> int:
        return self.cash_cents + sum(
            self._unrealized_cents(sym, pos) for sym, pos in self.positions.items()
        )

    def check_invariant(self, ts: datetime) -> None:
        recomputed = self.recompute_equity()
        if recomputed != self.equity_cents:
            msg = (
                f"accounting invariant broken at {ts}: incremental equity "
                f"{self.equity_cents} != cash+marks {recomputed}"
            )
            raise AccountingError(msg)

    def maintenance_margin_cents(self) -> int:
        return sum(
            abs(pos.quantity) * self._costs.spec(sym).maintenance_margin_cents
            for sym, pos in self.positions.items()
        )

    def check_margin(self, ts: datetime) -> None:
        """Record (not halt): margin discipline belongs to the risk engine
        (slice 4.6); the backtest only surfaces that it happened."""
        if self.maintenance_margin_cents() > self.equity_cents:
            self.margin_breaches.append(ts)

    def quantity(self, symbol: str) -> int:
        position = self.positions.get(symbol)
        return 0 if position is None else position.quantity

    # -- internals --------------------------------------------------------

    def _unrealized_cents(self, symbol: str, position: Position) -> int:
        tick_value = self._costs.spec(symbol).tick_value_cents
        return sum(
            (position.mark_ticks - lot.entry_ticks) * tick_value * lot.quantity
            for lot in position.lots
        )
