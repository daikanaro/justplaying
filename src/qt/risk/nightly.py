"""Nightly reconciliation: order journal vs the IBKR Flex statement (§4.6).

Per symbol and session date, the journal's fills must aggregate to the same
net quantity, traded value (to the cent), and commission totals as the
broker's statement. Any difference is reported and alerted — the §4.6
acceptance is 'nightly report matches broker statement'.

Date-bucketing caveat (documented, revisit against real Flex exports in 4.5):
journal fills bucket by UTC calendar date; the statement's TradeDate is the
broker's exchange-time trading day. For fills in the 17:00-19:00 CT evening
session the two can disagree by one day — a mismatch pair (extra on one date,
missing on the next) around the session open means bucketing skew, not lost
fills. If real statements show this routinely, both sides must move to
qt.data.sessions.trading_day.

The parser handles the Flex 'Trades' CSV section (Symbol, Quantity,
TradePrice, IBCommission, DateTime); fetching the Flex report itself needs
owner credentials and stays outside this module.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date

from qt.oms.journal import OrderJournal

_REQUIRED_COLUMNS = {"Symbol", "Quantity", "TradePrice", "IBCommission", "DateTime"}


class StatementError(Exception):
    """The broker statement is unreadable or malformed."""


@dataclass(frozen=True)
class StatementTrade:
    symbol: str
    quantity: int  # signed
    price: float
    commission_cents: int
    trade_date: date


@dataclass(frozen=True)
class SymbolTotals:
    net_quantity: int
    traded_value_cents: int  # sum of |qty| * price, in cents
    commission_cents: int


@dataclass(frozen=True)
class ReconDiff:
    symbol: str
    field: str
    journal_value: int
    broker_value: int


def parse_flex_trades(text: str) -> list[StatementTrade]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not _REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        msg = f"statement missing required columns {sorted(_REQUIRED_COLUMNS)}"
        raise StatementError(msg)
    trades: list[StatementTrade] = []
    for lineno, row in enumerate(reader, start=2):
        try:
            raw_dt = row["DateTime"].strip()
            trades.append(
                StatementTrade(
                    symbol=row["Symbol"].strip(),
                    quantity=int(float(row["Quantity"])),
                    price=float(row["TradePrice"]),
                    # IBKR reports commissions as negative amounts.
                    commission_cents=abs(round(float(row["IBCommission"]) * 100)),
                    trade_date=date.fromisoformat(raw_dt[:10].replace("/", "-")),
                )
            )
        except (KeyError, ValueError) as exc:
            msg = f"statement line {lineno}: {exc}"
            raise StatementError(msg) from exc
    return trades


def _totals_from_statement(trades: list[StatementTrade], day: date) -> dict[str, SymbolTotals]:
    out: dict[str, list[int]] = {}
    for trade in trades:
        if trade.trade_date != day:
            continue
        entry = out.setdefault(trade.symbol, [0, 0, 0])
        entry[0] += trade.quantity
        entry[1] += round(abs(trade.quantity) * trade.price * 100)
        entry[2] += trade.commission_cents
    return {s: SymbolTotals(*v) for s, v in out.items()}


def _totals_from_journal(journal: OrderJournal, day: date) -> dict[str, SymbolTotals]:
    out: dict[str, list[int]] = {}
    for fill in journal.fills():
        if fill.ts_utc[:10] != day.isoformat():
            continue
        sign = 1 if fill.side == "buy" else -1
        entry = out.setdefault(fill.symbol, [0, 0, 0])
        entry[0] += sign * fill.quantity
        entry[1] += round(fill.quantity * fill.price * 100)
    return {s: SymbolTotals(v[0], v[1], v[2]) for s, v in out.items()}


def reconcile_day(
    journal: OrderJournal,
    statement_trades: list[StatementTrade],
    day: date,
    compare_commissions: bool = False,
) -> list[ReconDiff]:
    """Diffs between journal and statement for ``day``; empty means matched.

    Commission comparison is optional because the journal does not yet carry
    per-fill commissions from the broker (they arrive with the statement);
    it turns on in 4.7 when the cost model is recalibrated from real fills.
    """
    journal_totals = _totals_from_journal(journal, day)
    broker_totals = _totals_from_statement(statement_trades, day)
    diffs: list[ReconDiff] = []
    for symbol in sorted(set(journal_totals) | set(broker_totals)):
        j = journal_totals.get(symbol, SymbolTotals(0, 0, 0))
        b = broker_totals.get(symbol, SymbolTotals(0, 0, 0))
        if j.net_quantity != b.net_quantity:
            diffs.append(ReconDiff(symbol, "net_quantity", j.net_quantity, b.net_quantity))
        if j.traded_value_cents != b.traded_value_cents:
            diffs.append(
                ReconDiff(symbol, "traded_value_cents", j.traded_value_cents, b.traded_value_cents)
            )
        if compare_commissions and j.commission_cents != b.commission_cents:
            diffs.append(
                ReconDiff(symbol, "commission_cents", j.commission_cents, b.commission_cents)
            )
    return diffs
