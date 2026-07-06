"""Fill simulation for one bar (§4 rules).

- Market: fills at bar open ± slippage (adverse), session-aware ticks.
- Stop: gap-through modeled — bar opens beyond the stop -> fill at open ± slip;
  otherwise touch -> fill at stop ± slip.
- Limit: conservative queue heuristic — fills only if price trades through the
  limit by >= 1 tick; price improvement at the open is honored.
- Partial fills: ``max_contracts_per_fill`` caps any single bar's fill;
  the remainder keeps working.

All fill prices are tick-aligned by construction (slippage is whole ticks and
input prices must be tick-aligned), which keeps cent accounting exact.
"""

from __future__ import annotations

from dataclasses import dataclass

from qt.backtest.events import Bar, FillEvent
from qt.backtest.orders import LimitOrder, MarketOrder, Order, Side, StopOrder
from qt.costs.model import CostModel


@dataclass(frozen=True)
class ExecutionConfig:
    max_contracts_per_fill: int | None = None  # None = no partial-fill cap

    def __post_init__(self) -> None:
        if self.max_contracts_per_fill is not None and self.max_contracts_per_fill < 1:
            msg = "max_contracts_per_fill must be >= 1 or None"
            raise ValueError(msg)


class ExecutionSimulator:
    def __init__(self, costs: CostModel, config: ExecutionConfig | None = None) -> None:
        self._costs = costs
        self._config = config or ExecutionConfig()

    def _fill_quantity(self, order: Order) -> int:
        if self._config.max_contracts_per_fill is None:
            return order.remaining
        return min(order.remaining, self._config.max_contracts_per_fill)

    def _make_fill(self, order: Order, bar: Bar, price: float, reason: str) -> FillEvent:
        quantity = self._fill_quantity(order)
        order.filled += quantity
        commission = self._costs.commission_cents(order.symbol, quantity)
        return FillEvent(
            ts=bar.ts,
            symbol=order.symbol,
            quantity=order.side.sign * quantity,
            price=price,
            commission_cents=commission,
            reason=reason,
        )

    def fill_market(self, order: MarketOrder, bar: Bar, reason: str) -> FillEvent:
        """Market order executing on this bar: open ± adverse slippage."""
        slip = self._costs.slippage_points(order.symbol, bar.ts)
        price = bar.open + order.side.sign * slip
        return self._make_fill(order, bar, price, reason)

    def fill_market_at_close(self, order: MarketOrder, bar: Bar, reason: str) -> FillEvent:
        """§3 S2 same-close mode (lookahead-adjacent): close ± adverse slippage."""
        slip = self._costs.slippage_points(order.symbol, bar.ts)
        price = bar.close + order.side.sign * slip
        return self._make_fill(order, bar, price, reason)

    def try_fill_stop(self, order: StopOrder, bar: Bar, reason: str) -> FillEvent | None:
        """Resting stop against this bar; None if not triggered."""
        slip = self._costs.slippage_points(order.symbol, bar.ts)
        if order.side is Side.SELL:  # protects a long: trigger at/below stop
            if bar.open <= order.stop_price:  # gapped through: fill at the worse open
                return self._make_fill(order, bar, bar.open - slip, reason)
            if bar.low <= order.stop_price:
                return self._make_fill(order, bar, order.stop_price - slip, reason)
            return None
        if bar.open >= order.stop_price:  # BUY stop protects a short
            return self._make_fill(order, bar, bar.open + slip, reason)
        if bar.high >= order.stop_price:
            return self._make_fill(order, bar, order.stop_price + slip, reason)
        return None

    def try_fill_limit(self, order: LimitOrder, bar: Bar, reason: str) -> FillEvent | None:
        """Resting limit: fills only on trade-through >= 1 tick (§4). No
        slippage — the limit price bounds execution; the open can improve it."""
        tick = self._costs.spec(order.symbol).tick_size
        if order.side is Side.BUY:
            if bar.open <= order.limit_price - tick:
                return self._make_fill(order, bar, bar.open, reason)
            if bar.low <= order.limit_price - tick:
                return self._make_fill(order, bar, order.limit_price, reason)
            return None
        if bar.open >= order.limit_price + tick:
            return self._make_fill(order, bar, bar.open, reason)
        if bar.high >= order.limit_price + tick:
            return self._make_fill(order, bar, order.limit_price, reason)
        return None
