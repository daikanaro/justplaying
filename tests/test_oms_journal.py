"""Order-journal tests: replay fidelity, crash tolerance, corruption limits."""

from pathlib import Path

import pytest

from qt.oms.journal import JournalError, OrderJournal
from qt.oms.state import OrderState


def journal(tmp_path: Path) -> OrderJournal:
    return OrderJournal(tmp_path / "orders.jsonl")


def test_replay_roundtrip(tmp_path: Path) -> None:
    j = journal(tmp_path)
    j.record_intent("QT-1", "MES", "buy", 2, "market")
    j.record_transition("QT-1", OrderState.ACKED)
    j.record_transition("QT-1", OrderState.FILLED, fill_quantity=2, fill_price=5000.25)
    j.record_intent("QT-2", "M2K", "sell", 3, "market")
    j.record_transition("QT-2", OrderState.PARTIAL, fill_quantity=1, fill_price=2000.10)
    replay = j.replay()
    assert replay.orders["QT-1"].state is OrderState.FILLED
    assert replay.orders["QT-2"].state is OrderState.PARTIAL
    assert replay.positions == {"MES": 2, "M2K": -1}
    assert not replay.truncated_tail
    assert j.known_ids() == {"QT-1", "QT-2"}


def test_replay_survives_process_restart(tmp_path: Path) -> None:
    journal(tmp_path).record_intent("QT-1", "MES", "buy", 1, "market")
    reopened = journal(tmp_path)  # fresh object, same file
    assert reopened.known_ids() == {"QT-1"}


def test_crash_truncated_tail_tolerated_and_flagged(tmp_path: Path) -> None:
    j = journal(tmp_path)
    j.record_intent("QT-1", "MES", "buy", 1, "market")
    with j.path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind": "transition", "client_or')  # crash mid-write
    replay = j.replay()
    assert replay.truncated_tail
    assert "QT-1" in replay.orders


def test_corrupt_middle_line_is_fatal(tmp_path: Path) -> None:
    j = journal(tmp_path)
    j.record_intent("QT-1", "MES", "buy", 1, "market")
    with j.path.open("a", encoding="utf-8") as fh:
        fh.write("garbage not json\n")
    j.record_intent("QT-2", "MES", "buy", 1, "market")
    with pytest.raises(JournalError, match="corrupt journal line"):
        j.replay()


def test_duplicate_intent_is_fatal(tmp_path: Path) -> None:
    j = journal(tmp_path)
    j.record_intent("QT-1", "MES", "buy", 1, "market")
    j.record_intent("QT-1", "MES", "buy", 1, "market")
    with pytest.raises(JournalError, match="duplicate intent"):
        j.replay()


def test_transition_for_unknown_order_is_fatal(tmp_path: Path) -> None:
    j = journal(tmp_path)
    j.record_transition("QT-ghost", OrderState.ACKED)
    with pytest.raises(JournalError, match="unknown order"):
        j.replay()


def test_illegal_journaled_sequence_is_fatal(tmp_path: Path) -> None:
    j = journal(tmp_path)
    j.record_intent("QT-1", "MES", "buy", 1, "market")
    j.record_transition("QT-1", OrderState.FILLED, fill_quantity=1)
    j.record_transition("QT-1", OrderState.ACKED)  # after terminal: impossible
    with pytest.raises(JournalError, match="illegal transition"):
        j.replay()
