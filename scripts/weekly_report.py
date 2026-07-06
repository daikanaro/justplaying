"""Generate the §4.7 weekly tracking-error report and advance the campaign clock.

Usage:
    uv run python scripts/weekly_report.py --week-start 2026-07-06 \
        --statement flex_trades.csv

Inputs: the order journal, the week's Flex trades CSV, daily equity snapshots
(data/journal/equity.jsonl), and research/campaign/expectations.json (written
from the backtest battery — OWNER reviews it):

    {"expected_trades_per_week": 4.0,
     "modeled_cost_per_round_trip_cents": 410,
     "annual_vol_target": 0.20}

Writes research/campaign/weekly_<start>.txt, updates the consecutive-weeks
clock (research/campaign_state.json), and prints the report + cost-model
recalibration suggestions. Exits 1 on an out-of-band week — diagnose before
restarting the clock.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from qt.campaign.equity_history import load_snapshots
from qt.campaign.recalibrate import suggest_costs
from qt.campaign.tracker import CampaignTracker
from qt.campaign.weekly import Expectations, build_weekly_report
from qt.config import InstrumentsConfig, RiskConfig, load_config
from qt.costs.model import CostModel
from qt.oms.journal import OrderJournal
from qt.risk.nightly import StatementError, parse_flex_trades

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = REPO_ROOT / "data" / "journal"
CAMPAIGN = REPO_ROOT / "research" / "campaign"
WEEK_DAYS = 6  # Monday .. Saturday-exclusive window: start + 6 covers Fri close


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", required=True, help="Monday, ISO date")
    parser.add_argument("--statement", type=Path, required=True)
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start)
    week_end = week_start + timedelta(days=WEEK_DAYS)

    expectations_path = CAMPAIGN / "expectations.json"
    if not expectations_path.is_file():
        print(
            f"BLOCKED: {expectations_path} missing — derive it from the validation "
            "battery (OWNER reviews the numbers) before the campaign starts",
            file=sys.stderr,
        )
        return 2
    raw = json.loads(expectations_path.read_text(encoding="utf-8"))
    expectations = Expectations(**raw)

    try:
        trades = parse_flex_trades(args.statement.read_text(encoding="utf-8"))
    except (OSError, StatementError) as exc:
        print(f"cannot read statement: {exc}", file=sys.stderr)
        return 2

    instruments = load_config(REPO_ROOT / "config" / "instruments.yaml", InstrumentsConfig)
    risk = load_config(REPO_ROOT / "config" / "risk.yaml", RiskConfig)
    costs = CostModel(instruments)
    journal = OrderJournal(RUNTIME / "orders.jsonl")
    fills = journal.fills()
    snapshots = load_snapshots(RUNTIME / "equity.jsonl")

    report = build_weekly_report(
        week_start, week_end, fills, trades, snapshots, expectations, costs
    )
    text = report.to_text()
    for symbol in risk.instrument_whitelist:
        text += "\n\n" + suggest_costs(fills, trades, costs, symbol).to_text()

    out = CAMPAIGN / f"weekly_{week_start.isoformat()}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)

    status = CampaignTracker(REPO_ROOT / "research" / "campaign_state.json").record_week(report)
    print(
        f"\ncampaign clock: {status.consecutive_in_band} consecutive in-band week(s) "
        f"of {status.total_weeks} total"
        + (" — ELIGIBLE for GO/NO-GO review" if status.eligible_for_go_nogo else "")
    )
    return 0 if report.inside_all_bands else 1


if __name__ == "__main__":
    raise SystemExit(main())
