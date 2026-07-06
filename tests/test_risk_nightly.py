"""Nightly reconciliation tests: journal vs Flex-statement fixtures."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.oms.journal import OrderJournal
from qt.oms.state import OrderState
from qt.risk.nightly import StatementError, parse_flex_trades, reconcile_day

TODAY = datetime.now(UTC).date()  # journal ts_utc stamps are 'now'
HEADER = "Symbol,Quantity,TradePrice,IBCommission,DateTime\n"


def statement(rows: list[str]) -> str:
    return HEADER + "\n".join(rows) + "\n"


def make_journal(tmp_path: Path) -> OrderJournal:
    journal = OrderJournal(tmp_path / "orders.jsonl")
    journal.record_intent("QT-1", "MES", "buy", 2, "market")
    journal.record_transition("QT-1", OrderState.FILLED, fill_quantity=2, fill_price=5000.25)
    journal.record_intent("QT-2", "M2K", "sell", 3, "market")
    journal.record_transition("QT-2", OrderState.PARTIAL, fill_quantity=1, fill_price=2000.10)
    journal.record_transition("QT-2", OrderState.FILLED, fill_quantity=2, fill_price=2000.00)
    return journal


def matching_rows() -> list[str]:
    return [
        f"MES,2,5000.25,-1.60,{TODAY}T14:31:00",
        f"M2K,-1,2000.10,-0.80,{TODAY}T15:02:00",
        f"M2K,-2,2000.00,-1.60,{TODAY}T15:03:00",
    ]


def test_parse_flex_trades() -> None:
    trades = parse_flex_trades(statement(matching_rows()))
    assert len(trades) == 3
    assert trades[0].symbol == "MES"
    assert trades[0].quantity == 2
    assert trades[0].commission_cents == 160  # sign normalized
    assert trades[1].quantity == -1
    assert trades[0].trade_date == TODAY


def test_matching_day_has_no_diffs(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    trades = parse_flex_trades(statement(matching_rows()))
    assert reconcile_day(journal, trades, TODAY) == []


def test_quantity_mismatch_detected(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    rows = [f"MES,1,5000.25,-0.80,{TODAY}T14:31:00", *matching_rows()[1:]]
    diffs = reconcile_day(journal, parse_flex_trades(statement(rows)), TODAY)
    fields = {(d.symbol, d.field) for d in diffs}
    assert ("MES", "net_quantity") in fields
    assert ("MES", "traded_value_cents") in fields


def test_price_mismatch_detected(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    rows = [f"MES,2,5001.25,-1.60,{TODAY}T14:31:00", *matching_rows()[1:]]
    diffs = reconcile_day(journal, parse_flex_trades(statement(rows)), TODAY)
    assert any(d.field == "traded_value_cents" and d.symbol == "MES" for d in diffs)
    assert not any(d.field == "net_quantity" for d in diffs)  # quantities still agree


def test_missing_and_extra_trades_detected(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    # Statement is missing M2K entirely and has a phantom MNQ trade.
    rows = [f"MES,2,5000.25,-1.60,{TODAY}T14:31:00", f"MNQ,1,18000.00,-0.80,{TODAY}T16:00:00"]
    diffs = reconcile_day(journal, parse_flex_trades(statement(rows)), TODAY)
    symbols = {d.symbol for d in diffs}
    assert "M2K" in symbols  # journal has it, broker doesn't
    assert "MNQ" in symbols  # broker has it, journal doesn't


def test_other_days_ignored(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)
    rows = [*matching_rows(), "MES,5,4900.00,-4.00,2020-01-02T14:31:00"]  # ancient trade
    assert reconcile_day(journal, parse_flex_trades(statement(rows)), TODAY) == []


def test_commission_compare_opt_in(tmp_path: Path) -> None:
    journal = make_journal(tmp_path)  # journal carries no commissions yet (4.7 wires them)
    trades = parse_flex_trades(statement(matching_rows()))
    assert reconcile_day(journal, trades, TODAY) == []  # off by default
    diffs = reconcile_day(journal, trades, TODAY, compare_commissions=True)
    assert any(d.field == "commission_cents" for d in diffs)


def test_malformed_statement_rejected() -> None:
    with pytest.raises(StatementError, match="required columns"):
        parse_flex_trades("Sym,Qty\nMES,1\n")
    with pytest.raises(StatementError, match="line 2"):
        parse_flex_trades(HEADER + "MES,notanumber,5000,-1.60,2026-07-06T14:00:00\n")
