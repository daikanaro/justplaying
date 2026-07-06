"""Submitter tests: idempotency (drill c), bounded backoff (drill d)."""

from pathlib import Path

import pytest

from qt.oms.alerts import LogAlerter
from qt.oms.journal import OrderJournal
from qt.oms.state import OrderState
from qt.oms.submitter import (
    OrderIntent,
    OrderSubmitter,
    OrderType,
    PlacementError,
    SubmitOutcome,
    backoff_delays,
)


def intent(decision: str = "S1/MES/t0") -> OrderIntent:
    return OrderIntent(decision, "MES", "buy", 2)


def test_client_order_id_is_deterministic_over_intent() -> None:
    a = intent()
    b = intent()
    assert a.client_order_id == b.client_order_id
    different_qty = OrderIntent("S1/MES/t0", "MES", "buy", 3)
    assert different_qty.client_order_id != a.client_order_id
    different_decision = intent("S1/MES/t1")
    assert different_decision.client_order_id != a.client_order_id


def test_intent_validation() -> None:
    with pytest.raises(ValueError, match="side"):
        OrderIntent("d", "MES", "hold", 1)
    with pytest.raises(ValueError, match="quantity"):
        OrderIntent("d", "MES", "buy", 0)
    with pytest.raises(ValueError, match="stop_price"):
        OrderIntent("d", "MES", "sell", 1, OrderType.STOP)


def test_duplicate_submit_suppressed(tmp_path: Path) -> None:
    journal = OrderJournal(tmp_path / "orders.jsonl")
    alerter = LogAlerter()
    placed: list[str] = []
    submitter = OrderSubmitter(journal, lambda i, oid: placed.append(oid), alerter, lambda s: None)
    assert submitter.submit(intent()) is SubmitOutcome.PLACED
    assert submitter.submit(intent()) is SubmitOutcome.DUPLICATE_SUPPRESSED
    assert len(placed) == 1
    assert len(journal.replay().orders) == 1
    assert any("duplicate" in m for m in alerter.messages)


def test_duplicate_suppressed_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "orders.jsonl"
    placed: list[str] = []
    first = OrderSubmitter(
        OrderJournal(path), lambda i, oid: placed.append(oid), LogAlerter(), lambda s: None
    )
    first.submit(intent())
    # New process, same journal file: the resend of the same decision is caught.
    second = OrderSubmitter(
        OrderJournal(path), lambda i, oid: placed.append(oid), LogAlerter(), lambda s: None
    )
    assert second.submit(intent()) is SubmitOutcome.DUPLICATE_SUPPRESSED
    assert len(placed) == 1


def test_backoff_delays_are_exponential_and_bounded() -> None:
    assert list(backoff_delays(2.0, 4)) == [2.0, 4.0, 8.0, 16.0]
    assert list(backoff_delays(2.0, 1)) == [2.0]


def test_forced_reject_no_retry_storm(tmp_path: Path) -> None:
    """Drill (d) at unit level: bounded attempts, backoff between them,
    exactly one alert, REJECTED journaled."""
    journal = OrderJournal(tmp_path / "orders.jsonl")
    alerter = LogAlerter()
    attempts = 0
    sleeps: list[float] = []

    def always_reject(i: OrderIntent, oid: str) -> None:
        nonlocal attempts
        attempts += 1
        msg = "margin reject"
        raise PlacementError(msg)

    submitter = OrderSubmitter(
        journal, always_reject, alerter, sleeps.append, max_attempts=3, backoff_base_s=2.0
    )
    outcome = submitter.submit(intent())
    assert outcome is SubmitOutcome.GAVE_UP
    assert attempts == 3  # bounded: exactly max_attempts, then stop
    assert sleeps == [2.0, 4.0]  # backoff between attempts, none after the last
    assert len(alerter.messages) == 1
    record = journal.replay().orders[intent().client_order_id]
    assert record.state is OrderState.REJECTED


def test_transient_failure_then_success(tmp_path: Path) -> None:
    journal = OrderJournal(tmp_path / "orders.jsonl")
    calls = 0

    def flaky(i: OrderIntent, oid: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "socket hiccup"
            raise PlacementError(msg)

    submitter = OrderSubmitter(journal, flaky, LogAlerter(), lambda s: None, max_attempts=3)
    assert submitter.submit(intent()) is SubmitOutcome.PLACED
    assert calls == 2
    record = journal.replay().orders[intent().client_order_id]
    assert record.state is OrderState.ACKED
