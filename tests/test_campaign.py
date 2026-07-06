"""Campaign tooling tests: the four §4.7 bands, the consecutive-weeks clock,
equity-vol math, and cost recalibration suggestions."""

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from qt.campaign.equity_history import (
    EquitySnapshot,
    append_snapshot,
    load_snapshots,
    realized_annual_vol,
)
from qt.campaign.recalibrate import suggest_costs
from qt.campaign.tracker import REQUIRED_CONSECUTIVE_WEEKS, CampaignError, CampaignTracker
from qt.campaign.weekly import BandCheck, Expectations, WeeklyReport, build_weekly_report
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel
from qt.oms.journal import FillRecord
from qt.risk.nightly import StatementTrade

WEEK_START = date(2026, 7, 6)  # Monday
WEEK_END = WEEK_START + timedelta(days=6)
RTH = datetime(2026, 7, 7, 15, 0, tzinfo=UTC)  # Tuesday 10:00 Chicago


@pytest.fixture(scope="module")
def costs(config_dir: Path) -> CostModel:
    return CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))


def expectations(trades_per_week: float = 2.0) -> Expectations:
    return Expectations(
        expected_trades_per_week=trades_per_week,
        modeled_cost_per_round_trip_cents=410.0,
        annual_vol_target=0.20,
    )


def fill(i: int, side: str, quantity: int, price: float, reference: float | None) -> FillRecord:
    return FillRecord(
        ts_utc=(RTH + timedelta(hours=i)).isoformat(),
        client_order_id=f"QT-{i}",
        symbol="MES",
        side=side,
        quantity=quantity,
        price=price,
        reference_price=reference,
    )


def statement_trade(quantity: int, price: float, commission_cents: int) -> StatementTrade:
    return StatementTrade(
        symbol="MES",
        quantity=quantity,
        price=price,
        commission_cents=commission_cents,
        trade_date=RTH.date(),
    )


def snapshots_with_daily_vol(daily_vol: float, n: int = 6) -> list[EquitySnapshot]:
    """Alternating +/-v returns -> stddev ~= v exactly (mean 0)."""
    equity = 10_000_000.0
    out = [EquitySnapshot(WEEK_START, round(equity))]
    for i in range(1, n):
        equity *= 1 + (daily_vol if i % 2 else -daily_vol)
        out.append(EquitySnapshot(WEEK_START + timedelta(days=i), round(equity)))
    return out


def in_band_inputs(costs: CostModel):  # type: ignore[no-untyped-def]
    # One round trip: buy 1 @ ref+1 tick (matches modeled RTH slippage), sell flat.
    fills = [
        fill(0, "buy", 1, 5000.25, 5000.00),
        fill(1, "sell", 1, 5009.75, 5010.00),
    ]
    # Commission $1.60 total + slippage 2 ticks x $1.25 = $2.50 -> $4.10/RT: modeled exactly.
    trades = [statement_trade(1, 5000.25, 80), statement_trade(-1, 5009.75, 80)]
    # Daily vol target 0.20/sqrt(252) ~= 1.26%: use 1.2% -> inside [0.25, 1.5] x target.
    snapshots = snapshots_with_daily_vol(0.012)
    return fills, trades, snapshots


def test_all_bands_inside(costs: CostModel) -> None:
    fills, trades, snapshots = in_band_inputs(costs)
    report = build_weekly_report(
        WEEK_START, WEEK_END, fills, trades, snapshots, expectations(trades_per_week=1.0), costs
    )
    assert report.n_round_trips == 1
    assert report.inside_all_bands, report.to_text()
    assert "INSIDE all bands" in report.to_text()


def test_slippage_band_trips_on_bad_fills(costs: CostModel) -> None:
    fills = [
        fill(0, "buy", 1, 5001.00, 5000.00),  # 4 ticks adverse vs 1 modeled
        fill(1, "sell", 1, 5009.00, 5010.00),  # 4 ticks adverse
    ]
    _, trades, snapshots = in_band_inputs(costs)
    report = build_weekly_report(
        WEEK_START, WEEK_END, fills, trades, snapshots, expectations(1.0), costs
    )
    slip = next(c for c in report.checks if c.name == "mean_slippage_ticks")
    assert not slip.in_band
    assert not report.inside_all_bands


def test_missing_reference_prices_fail_the_band(costs: CostModel) -> None:
    """No reference prices -> slippage is UNVERIFIABLE, which is out-of-band
    by policy: an unmeasured band must never count as passed."""
    fills = [fill(0, "buy", 1, 5000.25, None), fill(1, "sell", 1, 5009.75, None)]
    _, trades, snapshots = in_band_inputs(costs)
    report = build_weekly_report(
        WEEK_START, WEEK_END, fills, trades, snapshots, expectations(1.0), costs
    )
    slip = next(c for c in report.checks if c.name == "mean_slippage_ticks")
    assert not slip.in_band
    assert slip.observed is None


def test_trade_count_band(costs: CostModel) -> None:
    fills, trades, snapshots = in_band_inputs(costs)
    # 1 round trip vs expectation 2: 1 < 1.6 -> out of the +/-20% band.
    report = build_weekly_report(
        WEEK_START, WEEK_END, fills, trades, snapshots, expectations(2.0), costs
    )
    count = next(c for c in report.checks if c.name == "round_trips")
    assert not count.in_band


def test_vol_band_trips_on_dead_quiet_week(costs: CostModel) -> None:
    fills, trades, _ = in_band_inputs(costs)
    quiet = snapshots_with_daily_vol(0.0001)  # ~1.6% annual: below 0.25 x 20%
    report = build_weekly_report(
        WEEK_START, WEEK_END, fills, trades, quiet, expectations(1.0), costs
    )
    vol = next(c for c in report.checks if c.name == "realized_annual_vol")
    assert not vol.in_band


def test_cost_band_trips_on_expensive_week(costs: CostModel) -> None:
    fills, _, snapshots = in_band_inputs(costs)
    pricey = [statement_trade(1, 5000.25, 300), statement_trade(-1, 5009.75, 300)]
    report = build_weekly_report(
        WEEK_START, WEEK_END, fills, pricey, snapshots, expectations(1.0), costs
    )
    cost = next(c for c in report.checks if c.name == "cost_per_round_trip_cents")
    assert not cost.in_band  # $6.00 commissions + $2.50 slippage >> $4.10 x 1.25


def test_other_weeks_data_excluded(costs: CostModel) -> None:
    fills, trades, snapshots = in_band_inputs(costs)
    stale = fill(24 * 30, "buy", 1, 5100.25, 5100.00)  # a month later
    report = build_weekly_report(
        WEEK_START, WEEK_END, [*fills, stale], trades, snapshots, expectations(1.0), costs
    )
    assert report.n_fills == 2


# ---------------------------------------------------------------------------
# Campaign clock
# ---------------------------------------------------------------------------


def make_report(week: int, inside: bool) -> WeeklyReport:
    start = WEEK_START + timedelta(weeks=week)
    return WeeklyReport(
        week_start=start,
        week_end=start + timedelta(days=6),
        n_fills=2,
        n_round_trips=1,
        checks=[BandCheck("stub", 1.0, 1.0, inside, "test stub")],
    )


def test_four_consecutive_weeks_makes_eligible(tmp_path: Path) -> None:
    tracker = CampaignTracker(tmp_path / "campaign.json")
    for week in range(REQUIRED_CONSECUTIVE_WEEKS):
        status = tracker.record_week(make_report(week, inside=True))
    assert status.eligible_for_go_nogo
    assert status.consecutive_in_band == 4


def test_out_of_band_week_resets_the_clock(tmp_path: Path) -> None:
    tracker = CampaignTracker(tmp_path / "campaign.json")
    for week in range(3):
        tracker.record_week(make_report(week, inside=True))
    status = tracker.record_week(make_report(3, inside=False))  # restart the clock (§4.7)
    assert status.consecutive_in_band == 0
    assert not status.eligible_for_go_nogo
    for week in range(4, 8):
        status = tracker.record_week(make_report(week, inside=True))
    assert status.eligible_for_go_nogo
    assert status.total_weeks == 8


def test_clock_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "campaign.json"
    first = CampaignTracker(path)
    first.record_week(make_report(0, inside=True))
    reborn = CampaignTracker(path)
    assert reborn.status().consecutive_in_band == 1


def test_weeks_are_append_only(tmp_path: Path) -> None:
    tracker = CampaignTracker(tmp_path / "campaign.json")
    tracker.record_week(make_report(1, inside=True))
    with pytest.raises(CampaignError, match="append-only"):
        tracker.record_week(make_report(0, inside=True))  # older week
    with pytest.raises(CampaignError, match="append-only"):
        tracker.record_week(make_report(1, inside=True))  # duplicate week


# ---------------------------------------------------------------------------
# Equity history + recalibration
# ---------------------------------------------------------------------------


def test_equity_history_roundtrip_and_vol(tmp_path: Path) -> None:
    path = tmp_path / "equity.jsonl"
    for snapshot in snapshots_with_daily_vol(0.01, n=6):
        append_snapshot(path, snapshot)
    loaded = load_snapshots(path)
    assert len(loaded) == 6
    vol = realized_annual_vol(loaded)
    assert vol is not None
    assert vol == pytest.approx(0.01 * math.sqrt(252), rel=0.15)
    assert realized_annual_vol(loaded[:2]) is None  # too few points


def test_recalibration_suggestions(costs: CostModel) -> None:
    fills = [
        fill(0, "buy", 1, 5000.50, 5000.00),  # RTH, 2 ticks observed
        fill(1, "sell", 1, 5009.50, 5010.00),  # RTH, 2 ticks observed
    ]
    trades = [statement_trade(1, 5000.50, 100), statement_trade(-1, 5009.50, 100)]
    suggestions = suggest_costs(fills, trades, costs, "MES")
    assert suggestions.observed_commission_per_side_cents == pytest.approx(100.0)
    assert suggestions.configured_commission_per_side_cents == 80.0
    assert suggestions.observed_rth_slippage_ticks == pytest.approx(2.0)
    assert suggestions.configured_rth_slippage_ticks == 1
    assert suggestions.observed_eth_slippage_ticks is None
    text = suggestions.to_text()
    assert "observed 100.00 vs configured 80" in text
    assert "never" not in text  # suggestions, not commands — but no auto-edit happens
