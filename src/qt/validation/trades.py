"""Round-trip extraction from fill streams (production twin of the KA helper).

Net cents per flat-to-flat episode, FIFO within the episode, commissions from
the fills themselves. Reversals split correctly (one fill can close a trade
and open the next at the same price). An open position at stream end is NOT a
trade — unrealized tails belong to the equity curve, not the trade list.
"""

from __future__ import annotations

from qt.backtest.events import FillEvent
from qt.costs.model import CostModel


def round_trips(fills: list[FillEvent], costs: CostModel) -> list[int]:
    trades: list[int] = []
    # All episode state is PER SYMBOL: a shared position would net MES fills
    # against M2K fills and invent flat-to-flat boundaries that never happened.
    positions: dict[str, int] = {}
    entry_lots: dict[str, list[tuple[int, int]]] = {}  # (signed qty, entry ticks)
    open_pnl_cents: dict[str, int] = {}

    for fill in fills:
        symbol = fill.symbol
        tick_value = costs.spec(symbol).tick_value_cents
        price_ticks = costs.price_to_ticks(symbol, fill.price)
        quantity = fill.quantity
        per_contract_commission = fill.commission_cents // abs(quantity)
        position = positions.get(symbol, 0)
        lots = entry_lots.setdefault(symbol, [])
        pnl = open_pnl_cents.get(symbol, 0)
        while quantity != 0:
            if position == 0:
                lots[:] = [(quantity, price_ticks)]
                pnl = -per_contract_commission * abs(quantity)
                position = quantity
                quantity = 0
            elif (position > 0) != (quantity > 0):
                lot_qty, lot_ticks = lots[0]
                direction = 1 if lot_qty > 0 else -1
                closed = min(abs(quantity), abs(lot_qty))
                pnl += (
                    price_ticks - lot_ticks
                ) * tick_value * direction * closed - per_contract_commission * closed
                lot_qty -= direction * closed
                quantity += direction * closed
                position -= direction * closed
                if lot_qty == 0:
                    lots.pop(0)
                else:
                    lots[0] = (lot_qty, lot_ticks)
                if position == 0:
                    trades.append(pnl)
                    pnl = 0
            else:
                lots.append((quantity, price_ticks))
                pnl -= per_contract_commission * abs(quantity)
                position += quantity
                quantity = 0
        positions[symbol] = position
        open_pnl_cents[symbol] = pnl
    return trades
