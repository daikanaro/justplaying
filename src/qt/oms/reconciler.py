"""Target-position reconciler + startup/reconnect full reconciliation (§4.5).

The reconciler loop is a pure diff: targets vs broker positions vs working
orders -> delta intents. Full reconciliation compares the journal's replayed
positions against the broker's; ANY unexplained difference writes the HALT
flag, emits an alert, and raises — the engine never trades on a state it
cannot explain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qt.oms.alerts import Alerter
from qt.oms.halt import HaltError, write_halt
from qt.oms.journal import OrderJournal


@dataclass(frozen=True)
class PositionDelta:
    symbol: str
    quantity: int  # signed: >0 buy, <0 sell


def target_deltas(
    targets: dict[str, int],
    broker_positions: dict[str, int],
    working_quantities: dict[str, int],
) -> list[PositionDelta]:
    """Delta orders that move broker + working to the targets. Working orders
    count toward the expected position so the loop never double-orders."""
    deltas: list[PositionDelta] = []
    for symbol in sorted(set(targets) | set(broker_positions) | set(working_quantities)):
        expected = broker_positions.get(symbol, 0) + working_quantities.get(symbol, 0)
        delta = targets.get(symbol, 0) - expected
        if delta != 0:
            deltas.append(PositionDelta(symbol=symbol, quantity=delta))
    return deltas


@dataclass(frozen=True)
class Mismatch:
    symbol: str
    journal_quantity: int
    broker_quantity: int


def position_mismatches(
    journal_positions: dict[str, int], broker_positions: dict[str, int]
) -> list[Mismatch]:
    out: list[Mismatch] = []
    for symbol in sorted(set(journal_positions) | set(broker_positions)):
        journal_quantity = journal_positions.get(symbol, 0)
        broker_quantity = broker_positions.get(symbol, 0)
        if journal_quantity != broker_quantity:
            out.append(Mismatch(symbol, journal_quantity, broker_quantity))
    return out


def full_reconciliation(
    journal: OrderJournal,
    broker_positions: dict[str, int],
    halt_path: Path,
    alerter: Alerter,
) -> None:
    """Startup/reconnect gate: journal must equal broker, or we halt.

    Raises HaltError after writing the flag; the engine must not catch it.
    A journal with a crash-truncated tail also halts — the missing record is
    precisely the kind of unexplained state this exists to catch.
    """
    replay = journal.replay()
    problems: list[str] = []
    if replay.truncated_tail:
        problems.append("journal has a crash-truncated final record")
    problems.extend(
        f"order {order_id} ({record.symbol}) journaled but never progressed past "
        "PENDING_NEW — crash between intent and ack; resolve against broker open orders"
        for order_id, record in replay.orders.items()
        if record.state.value == "PENDING_NEW"
    )
    problems.extend(
        f"{m.symbol}: journal says {m.journal_quantity}, broker says {m.broker_quantity}"
        for m in position_mismatches(replay.positions, broker_positions)
    )
    if not problems:
        return
    reason = "reconciliation mismatch: " + "; ".join(problems)
    write_halt(halt_path, reason)
    alerter.alert(reason)
    raise HaltError(reason)
