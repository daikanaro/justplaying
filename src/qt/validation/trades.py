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
    position = 0
    entry_lots: list[tuple[int, int]] = []  # (signed qty, entry ticks)
    open_pnl_cents = 0

    for fill in fills:
        symbol = fill.symbol
        tick_value = costs.spec(symbol).tick_value_cents
        price_ticks = costs.price_to_ticks(symbol, fill.price)
        quantity = fill.quantity
        per_contract_commission = fill.commission_cents // abs(quantity)
        while quantity != 0:
            if position == 0:
                entry_lots = [(quantity, price_ticks)]
                open_pnl_cents = -per_contract_commission * abs(quantity)
                position = quantity
                quantity = 0
            elif (position > 0) != (quantity > 0):
                lot_qty, lot_ticks = entry_lots[0]
                direction = 1 if lot_qty > 0 else -1
                closed = min(abs(quantity), abs(lot_qty))
                open_pnl_cents += (
                    price_ticks - lot_ticks
                ) * tick_value * direction * closed - per_contract_commission * closed
                lot_qty -= direction * closed
                quantity += direction * closed
                position -= direction * closed
                if lot_qty == 0:
                    entry_lots.pop(0)
                else:
                    entry_lots[0] = (lot_qty, lot_ticks)
                if position == 0:
                    trades.append(open_pnl_cents)
                    open_pnl_cents = 0
            else:
                entry_lots.append((quantity, price_ticks))
                open_pnl_cents -= per_contract_commission * abs(quantity)
                position += quantity
                quantity = 0
    return trades
