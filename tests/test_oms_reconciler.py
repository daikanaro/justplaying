"""Reconciler tests: target deltas, mismatch -> HALT + alert, halt semantics."""

from pathlib import Path

import pytest

from qt.oms.alerts import LogAlerter
from qt.oms.halt import HaltError, require_not_halted, write_halt
from qt.oms.journal import OrderJournal
from qt.oms.reconciler import (
    Mismatch,
    PositionDelta,
    full_reconciliation,
    position_mismatches,
    target_deltas,
)
from qt.oms.state import OrderState


def test_target_deltas_basic() -> None:
    deltas = target_deltas({"MES": 2, "M2K": -3}, {"MES": 0, "M2K": 0}, {})
    assert deltas == [PositionDelta("M2K", -3), PositionDelta("MES", 2)]


def test_working_orders_count_toward_expected() -> None:
    # Broker flat, 2 already working: no double-order.
    assert target_deltas({"MES": 2}, {}, {"MES": 2}) == []
    # 1 working, need 2: order only the missing 1.
    assert target_deltas({"MES": 2}, {}, {"MES": 1}) == [PositionDelta("MES", 1)]


def test_overshoot_produces_corrective_delta() -> None:
    assert target_deltas({"MES": 1}, {"MES": 3}, {}) == [PositionDelta("MES", -2)]
    assert target_deltas({}, {"MES": 2}, {}) == [PositionDelta("MES", -2)]  # stray position


def test_position_mismatches_zero_equivalence() -> None:
    assert position_mismatches({"MES": 0}, {}) == []
    assert position_mismatches({}, {"MES": 0}) == []
    assert position_mismatches({"MES": 1}, {"MES": -1}) == [Mismatch("MES", 1, -1)]


def _journal_with_position(tmp_path: Path, symbol: str, quantity: int) -> OrderJournal:
    journal = OrderJournal(tmp_path / "orders.jsonl")
    side = "buy" if quantity > 0 else "sell"
    journal.record_intent("QT-1", symbol, side, abs(quantity), "market")
    journal.record_transition("QT-1", OrderState.FILLED, fill_quantity=abs(quantity))
    return journal


def test_full_reconciliation_clean(tmp_path: Path) -> None:
    journal = _journal_with_position(tmp_path, "MES", 2)
    halt = tmp_path / "HALT"
    full_reconciliation(journal, {"MES": 2}, halt, LogAlerter())  # no raise
    assert not halt.exists()


def test_full_reconciliation_mismatch_halts_and_alerts(tmp_path: Path) -> None:
    journal = _journal_with_position(tmp_path, "MES", 2)
    halt = tmp_path / "HALT"
    alerter = LogAlerter()
    with pytest.raises(HaltError, match="MES: journal says 2, broker says 1"):
        full_reconciliation(journal, {"MES": 1}, halt, alerter)
    assert halt.exists()
    assert "journal says 2" in halt.read_text(encoding="utf-8")
    assert len(alerter.messages) == 1
    # And the engine now refuses to start until the OWNER deletes the flag.
    with pytest.raises(HaltError, match="refuses to start"):
        require_not_halted(halt)


def test_truncated_journal_tail_halts(tmp_path: Path) -> None:
    journal = _journal_with_position(tmp_path, "MES", 2)
    with journal.path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind": "transition", "cli')  # crash mid-write
    halt = tmp_path / "HALT"
    with pytest.raises(HaltError, match="crash-truncated"):
        full_reconciliation(journal, {"MES": 2}, halt, LogAlerter())
    assert halt.exists()


def test_halt_reasons_accumulate(tmp_path: Path) -> None:
    halt = tmp_path / "HALT"
    write_halt(halt, "first incident")
    write_halt(halt, "second incident")
    content = halt.read_text(encoding="utf-8")
    assert "first incident" in content
    assert "second incident" in content


def test_require_not_halted_passes_without_flag(tmp_path: Path) -> None:
    require_not_halted(tmp_path / "HALT")  # no flag, no raise
