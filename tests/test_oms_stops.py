"""Native stop manager tests: create, ratchet, never widen, flip, release."""

from itertools import count

import pytest

from qt.oms.stops import NativeStopManager, StopSide, StopWideningError


class FakeBroker:
    def __init__(self) -> None:
        self._ids = count(1)
        self.placed: list[tuple[str, StopSide, int, float]] = []
        self.modified: list[tuple[str, float, int]] = []
        self.cancelled: list[str] = []

    def place(self, symbol: str, side: StopSide, quantity: int, price: float) -> str:
        self.placed.append((symbol, side, quantity, price))
        return f"IB-{next(self._ids)}"

    def modify(self, broker_id: str, price: float, quantity: int) -> None:
        self.modified.append((broker_id, price, quantity))

    def cancel(self, broker_id: str) -> None:
        self.cancelled.append(broker_id)


def manager() -> tuple[NativeStopManager, FakeBroker]:
    broker = FakeBroker()
    return NativeStopManager(broker.place, broker.modify, broker.cancel), broker


def test_create_then_ratchet_up_for_long() -> None:
    mgr, broker = manager()
    stop = mgr.upsert("MES", StopSide.SELL, 2, 4990.0)
    assert broker.placed == [("MES", StopSide.SELL, 2, 4990.0)]
    ratcheted = mgr.upsert("MES", StopSide.SELL, 2, 4995.0)
    assert ratcheted.broker_order_id == stop.broker_order_id  # modified, not replaced
    assert broker.modified == [(stop.broker_order_id, 4995.0, 2)]


def test_widening_long_stop_is_impossible() -> None:
    mgr, _ = manager()
    mgr.upsert("MES", StopSide.SELL, 2, 4990.0)
    with pytest.raises(StopWideningError, match="widens"):
        mgr.upsert("MES", StopSide.SELL, 2, 4985.0)


def test_widening_short_stop_is_impossible() -> None:
    mgr, _ = manager()
    mgr.upsert("MES", StopSide.BUY, 1, 5010.0)
    with pytest.raises(StopWideningError, match="widens"):
        mgr.upsert("MES", StopSide.BUY, 1, 5015.0)
    mgr.upsert("MES", StopSide.BUY, 1, 5005.0)  # tightening down is the ratchet


def test_flip_replaces_stop_via_cancel_and_place() -> None:
    mgr, broker = manager()
    first = mgr.upsert("MES", StopSide.SELL, 2, 4990.0)
    flipped = mgr.upsert("MES", StopSide.BUY, 2, 5010.0)  # position flipped short
    assert broker.cancelled == [first.broker_order_id]
    assert flipped.broker_order_id != first.broker_order_id
    # The new BUY stop is free of the old SELL stop's ratchet history.
    mgr.upsert("MES", StopSide.BUY, 2, 5008.0)


def test_resize_same_price_modifies_quantity() -> None:
    mgr, broker = manager()
    stop = mgr.upsert("MES", StopSide.SELL, 3, 4990.0)
    mgr.upsert("MES", StopSide.SELL, 1, 4990.0)  # position partially closed
    assert broker.modified == [(stop.broker_order_id, 4990.0, 1)]


def test_no_op_upsert_causes_no_broker_chatter() -> None:
    mgr, broker = manager()
    mgr.upsert("MES", StopSide.SELL, 2, 4990.0)
    mgr.upsert("MES", StopSide.SELL, 2, 4990.0)
    assert broker.modified == []
    assert len(broker.placed) == 1


def test_release_cancels_and_forgets() -> None:
    mgr, broker = manager()
    stop = mgr.upsert("MES", StopSide.SELL, 2, 4990.0)
    mgr.release("MES")
    assert broker.cancelled == [stop.broker_order_id]
    assert mgr.current("MES") is None
    mgr.release("MES")  # idempotent
    # After release, a fresh stop can be placed anywhere — no stale ratchet.
    mgr.upsert("MES", StopSide.SELL, 1, 4980.0)


def test_validation() -> None:
    mgr, _ = manager()
    with pytest.raises(ValueError, match="quantity"):
        mgr.upsert("MES", StopSide.SELL, 0, 4990.0)
    with pytest.raises(ValueError, match="price"):
        mgr.upsert("MES", StopSide.SELL, 1, 0.0)
