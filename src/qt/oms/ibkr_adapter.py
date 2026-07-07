"""Thin ib_async adapter for the OMS (§4.5). Everything above this module is
broker-agnostic and unit-tested; this file only translates and connects.

Gateway lifecycle: IB Gateway restarts daily (docs/windows_ops.md). The
adapter treats every (re)connect the same way: connect, snapshot broker
positions, run full reconciliation against the journal, and only then hand
control back. A reconciliation mismatch halts (flag + alert + raise) — the
engine never trades on unexplained state.

The pure translation helpers are unit-tested; connect/submit paths require a
running Gateway with a paper login (OWNER item §6) and are exercised by
scripts/chaos_drills.py once that exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qt.oms.alerts import Alerter
from qt.oms.halt import require_not_halted
from qt.oms.journal import OrderJournal
from qt.oms.reconciler import full_reconciliation
from qt.oms.submitter import OrderIntent, OrderType


class GatewayUnavailableError(Exception):
    """IB Gateway is not reachable — an OWNER item, never worked around."""


def to_ib_order_kwargs(intent: OrderIntent, client_order_id: str) -> dict[str, Any]:
    """Translate an OrderIntent into ib_async Order fields. ``orderRef``
    carries the client order id so broker state maps back to the journal."""
    kwargs: dict[str, Any] = {
        "action": "BUY" if intent.side == "buy" else "SELL",
        "totalQuantity": intent.quantity,
        "orderRef": client_order_id,
        "tif": "GTC" if intent.order_type is OrderType.STOP else "DAY",
    }
    if intent.order_type is OrderType.MARKET:
        kwargs["orderType"] = "MKT"
    else:
        kwargs["orderType"] = "STP"
        kwargs["auxPrice"] = intent.stop_price
    return kwargs


def to_ib_contract_kwargs(symbol: str, local_symbol: str) -> dict[str, Any]:
    return {
        "secType": "FUT",
        "symbol": symbol,
        "localSymbol": local_symbol,
        "exchange": "CME",
        "currency": "USD",
    }


class IbkrOms:
    """Connection wrapper: connect -> reconcile -> trade; reconnect repeats it."""

    def __init__(  # noqa: PLR0913 - connection endpoint is owner-tunable
        self,
        journal: OrderJournal,
        halt_path: Path,
        alerter: Alerter,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 21,
    ) -> None:
        self._journal = journal
        self._halt_path = halt_path
        self._alerter = alerter
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib: Any = None

    async def connect(self) -> None:
        """Connect and gate on reconciliation. Raises HaltError on mismatch,
        GatewayUnavailableError when there is nothing to connect to."""
        require_not_halted(self._halt_path)
        import asyncio  # noqa: PLC0415 - keep module importable without an event loop

        from ib_async import IB  # noqa: PLC0415 - heavy import, gateway-only path

        ib = IB()
        try:
            await ib.connectAsync(self._host, self._port, clientId=self._client_id, timeout=10.0)
        except (TimeoutError, OSError, asyncio.CancelledError) as exc:
            msg = (
                f"cannot reach IB Gateway at {self._host}:{self._port} — OWNER ACTION (§6): "
                "paper login + running Gateway required"
            )
            raise GatewayUnavailableError(msg) from exc
        self._ib = ib
        # SUM per root symbol: two contract months of the same root must
        # aggregate, not overwrite each other (dict-comprehension last-wins).
        broker_positions: dict[str, int] = {}
        for p in ib.positions():
            if p.position:
                symbol = p.contract.symbol
                broker_positions[symbol] = broker_positions.get(symbol, 0) + int(p.position)
        # Mismatch writes HALT + alerts + raises; we must not catch it.
        full_reconciliation(self._journal, broker_positions, self._halt_path, self._alerter)

    def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()
            self._ib = None

    @property
    def connected(self) -> bool:
        return self._ib is not None and bool(self._ib.isConnected())
