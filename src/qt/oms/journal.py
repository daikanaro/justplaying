"""Append-only order journal (JSONL, fsync'd per record).

The journal is the engine's memory across crashes and Gateway restarts:
startup/reconnect reconciliation replays it and compares against the broker.
There is deliberately no rewrite/delete API. A corrupt FINAL line (crash
mid-write) is tolerated and reported; corruption anywhere else is fatal.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qt.oms.state import IllegalTransitionError, OrderRecord, OrderState


class JournalError(Exception):
    """The journal is corrupt beyond the crash-tolerant final line."""


@dataclass(frozen=True)
class ReplayResult:
    orders: dict[str, OrderRecord]
    positions: dict[str, int]  # signed net contracts per symbol, from fills
    truncated_tail: bool  # a corrupt final line was dropped (crash mid-write)


class OrderJournal:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    # -- writing ------------------------------------------------------------

    def _append(self, record: dict[str, Any]) -> None:
        record = {"ts_utc": datetime.now(UTC).isoformat(timespec="milliseconds"), **record}
        line = json.dumps(record, sort_keys=True, default=str)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def record_intent(  # noqa: PLR0913 - one journal field per order attribute
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        stop_price: float | None = None,
    ) -> None:
        self._append(
            {
                "kind": "intent",
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": order_type,
                "stop_price": stop_price,
            }
        )

    def record_transition(
        self,
        client_order_id: str,
        state: OrderState,
        fill_quantity: int = 0,
        fill_price: float | None = None,
        note: str = "",
    ) -> None:
        self._append(
            {
                "kind": "transition",
                "client_order_id": client_order_id,
                "state": state.value,
                "fill_quantity": fill_quantity,
                "fill_price": fill_price,
                "note": note,
            }
        )

    # -- reading ------------------------------------------------------------

    def known_ids(self) -> set[str]:
        return set(self.replay().orders)

    def replay(self) -> ReplayResult:
        """Rebuild order + position state from the journal, via the SAME state
        machine live trading uses — an illegal journaled sequence is fatal."""
        orders: dict[str, OrderRecord] = {}
        sides: dict[str, int] = {}
        positions: dict[str, int] = {}
        truncated = False
        lines = self._path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                if lineno == len(lines):
                    truncated = True  # crash mid-write: drop the tail, note it
                    break
                msg = f"{self._path}:{lineno}: corrupt journal line: {exc}"
                raise JournalError(msg) from exc
            self._apply(record, orders, sides, positions, lineno)
        return ReplayResult(orders=orders, positions=positions, truncated_tail=truncated)

    def _apply(
        self,
        record: dict[str, Any],
        orders: dict[str, OrderRecord],
        sides: dict[str, int],
        positions: dict[str, int],
        lineno: int,
    ) -> None:
        kind = record.get("kind")
        order_id = record.get("client_order_id", "")
        if kind == "intent":
            if order_id in orders:
                msg = f"{self._path}:{lineno}: duplicate intent for {order_id}"
                raise JournalError(msg)
            orders[order_id] = OrderRecord(
                client_order_id=order_id,
                symbol=record["symbol"],
                quantity=int(record["quantity"]),
            )
            sides[order_id] = 1 if record["side"] == "buy" else -1
        elif kind == "transition":
            if order_id not in orders:
                msg = f"{self._path}:{lineno}: transition for unknown order {order_id}"
                raise JournalError(msg)
            order = orders[order_id]
            fill_quantity = int(record.get("fill_quantity", 0))
            try:
                order.transition(OrderState(record["state"]), fill_quantity)
            except IllegalTransitionError as exc:
                msg = f"{self._path}:{lineno}: journaled illegal transition: {exc}"
                raise JournalError(msg) from exc
            if fill_quantity:
                symbol = order.symbol
                positions[symbol] = positions.get(symbol, 0) + sides[order_id] * fill_quantity
        else:
            msg = f"{self._path}:{lineno}: unknown journal record kind {kind!r}"
            raise JournalError(msg)
