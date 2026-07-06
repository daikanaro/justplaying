"""Adapter translation tests (pure parts only; the connect path needs a
Gateway and is exercised by scripts/chaos_drills.py)."""

from pathlib import Path

import pytest

from qt.oms.alerts import LogAlerter
from qt.oms.halt import HaltError, write_halt
from qt.oms.ibkr_adapter import IbkrOms, to_ib_contract_kwargs, to_ib_order_kwargs
from qt.oms.journal import OrderJournal
from qt.oms.submitter import OrderIntent, OrderType


def test_market_order_mapping() -> None:
    intent = OrderIntent("d1", "MES", "buy", 2)
    kwargs = to_ib_order_kwargs(intent, "QT-abc")
    assert kwargs == {
        "action": "BUY",
        "totalQuantity": 2,
        "orderRef": "QT-abc",
        "tif": "DAY",
        "orderType": "MKT",
    }


def test_stop_order_mapping_is_gtc_with_aux_price() -> None:
    intent = OrderIntent("d2", "MES", "sell", 1, OrderType.STOP, stop_price=4990.0)
    kwargs = to_ib_order_kwargs(intent, "QT-def")
    assert kwargs["orderType"] == "STP"
    assert kwargs["auxPrice"] == 4990.0
    assert kwargs["action"] == "SELL"
    assert kwargs["tif"] == "GTC"  # protective stops rest across sessions


def test_contract_mapping() -> None:
    assert to_ib_contract_kwargs("MES", "MESU5") == {
        "secType": "FUT",
        "symbol": "MES",
        "localSymbol": "MESU5",
        "exchange": "CME",
        "currency": "USD",
    }


@pytest.mark.anyio
async def test_connect_refuses_while_halted(tmp_path: Path) -> None:
    """The halt gate fires BEFORE any connection attempt."""
    halt = tmp_path / "HALT"
    write_halt(halt, "prior incident")
    oms = IbkrOms(OrderJournal(tmp_path / "orders.jsonl"), halt, LogAlerter())
    with pytest.raises(HaltError, match="refuses to start"):
        await oms.connect()


def test_disconnected_by_default(tmp_path: Path) -> None:
    oms = IbkrOms(OrderJournal(tmp_path / "orders.jsonl"), tmp_path / "HALT", LogAlerter())
    assert not oms.connected
