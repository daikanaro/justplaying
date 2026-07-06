"""Nightly reconciliation: order journal vs an IBKR Flex statement CSV (§4.6).

Usage:
    uv run python scripts/nightly_recon.py --statement flex_trades.csv [--date 2026-07-06]

Exits 0 when the journal matches the statement for the day, 1 with a diff
report otherwise. Fetching the Flex report is an owner-credentialed step;
this consumes the downloaded CSV.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from qt.oms.journal import OrderJournal
from qt.risk.nightly import StatementError, parse_flex_trades, reconcile_day

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNAL = REPO_ROOT / "data" / "journal" / "orders.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--date", default=datetime.now(UTC).date().isoformat())
    args = parser.parse_args()

    try:
        trades = parse_flex_trades(args.statement.read_text(encoding="utf-8"))
    except (OSError, StatementError) as exc:
        print(f"cannot read statement: {exc}", file=sys.stderr)
        return 2
    day = datetime.fromisoformat(args.date).date()
    diffs = reconcile_day(OrderJournal(JOURNAL), trades, day)
    if not diffs:
        print(f"{day}: journal matches broker statement")
        return 0
    print(f"{day}: {len(diffs)} reconciliation differences:", file=sys.stderr)
    for diff in diffs:
        print(
            f"  {diff.symbol} {diff.field}: journal {diff.journal_value} "
            f"!= broker {diff.broker_value}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
