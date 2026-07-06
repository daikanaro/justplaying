"""The weekly tracking-error report (§4.7). Four bands, all from the plan:

1. mean fill slippage vs modeled within +/-1 tick,
2. trade count vs backtest expectation within +/-20%,
3. realized portfolio vol inside the target band,
4. cost per round trip within +/-25% of modeled.

An out-of-band week is not a formatting detail — it resets the campaign clock
(qt.campaign.tracker) and demands a diagnosis before the clock restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from qt.campaign.equity_history import EquitySnapshot, realized_annual_vol
from qt.costs.model import CostModel
from qt.oms.journal import FillRecord
from qt.risk.nightly import StatementTrade

SLIPPAGE_BAND_TICKS = 1.0  # +/-1 tick (plan)
TRADE_COUNT_BAND = 0.20  # +/-20% (plan)
COST_BAND = 0.25  # +/-25% (plan)


@dataclass(frozen=True)
class Expectations:
    """Backtest-derived yardsticks, written by the owner/battery — inputs,
    never computed inside the report (no self-grading)."""

    expected_trades_per_week: float
    modeled_cost_per_round_trip_cents: float
    annual_vol_target: float  # §1 overlay target, e.g. 0.20
    vol_band_low: float = 0.25  # fractions of target: realized in [low, high] x target
    vol_band_high: float = 1.50

    def __post_init__(self) -> None:
        if self.expected_trades_per_week <= 0 or self.modeled_cost_per_round_trip_cents <= 0:
            msg = "expectations must be positive"
            raise ValueError(msg)
        if not 0 < self.vol_band_low < self.vol_band_high:
            msg = f"bad vol band [{self.vol_band_low}, {self.vol_band_high}]"
            raise ValueError(msg)


@dataclass(frozen=True)
class BandCheck:
    name: str
    observed: float | None  # None = not measurable this week
    expected: float
    in_band: bool
    detail: str


@dataclass(frozen=True)
class WeeklyReport:
    week_start: date
    week_end: date
    n_fills: int
    n_round_trips: int
    checks: list[BandCheck]

    @property
    def inside_all_bands(self) -> bool:
        return all(c.in_band for c in self.checks)

    def to_text(self) -> str:
        lines = [
            f"weekly tracking report {self.week_start} .. {self.week_end} — "
            f"{'INSIDE all bands' if self.inside_all_bands else 'OUT OF BAND'}",
            f"fills: {self.n_fills}, round trips: {self.n_round_trips}",
        ]
        for check in self.checks:
            status = "ok " if check.in_band else "OUT"
            observed = "n/a" if check.observed is None else f"{check.observed:.3f}"
            lines.append(
                f"  [{status}] {check.name}: observed {observed} vs expected "
                f"{check.expected:.3f} — {check.detail}"
            )
        return "\n".join(lines)


def _in_week(ts_utc: str, start: date, end: date) -> bool:
    day = datetime.fromisoformat(ts_utc).date()
    return start <= day <= end


def _round_trip_count(fills: list[FillRecord]) -> int:
    position = 0
    trips = 0
    for fill in fills:
        signed = fill.quantity if fill.side == "buy" else -fill.quantity
        before = position
        position += signed
        if before != 0 and (position == 0 or before * position < 0):
            trips += 1
    return trips


def _mean_slippage_ticks(fills: list[FillRecord], costs: CostModel) -> tuple[float, float] | None:
    """(mean observed adverse ticks, mean modeled ticks) over reference-priced
    fills; None when no fill carries a reference price."""
    observed: list[float] = []
    modeled: list[float] = []
    for fill in fills:
        if fill.reference_price is None:
            continue
        tick = costs.spec(fill.symbol).tick_size
        sign = 1 if fill.side == "buy" else -1
        observed.append(sign * (fill.price - fill.reference_price) / tick)
        modeled.append(float(costs.slippage_ticks(datetime.fromisoformat(fill.ts_utc))))
    if not observed:
        return None
    return sum(observed) / len(observed), sum(modeled) / len(modeled)


def build_weekly_report(  # noqa: PLR0913 - the report consumes exactly these sources
    week_start: date,
    week_end: date,
    fills: list[FillRecord],
    statement_trades: list[StatementTrade],
    snapshots: list[EquitySnapshot],
    expectations: Expectations,
    costs: CostModel,
) -> WeeklyReport:
    if week_end < week_start:
        msg = f"week_end {week_end} before week_start {week_start}"
        raise ValueError(msg)
    week_fills = [f for f in fills if _in_week(f.ts_utc, week_start, week_end)]
    week_snapshots = [s for s in snapshots if week_start <= s.day <= week_end]
    week_statement = [t for t in statement_trades if week_start <= t.trade_date <= week_end]
    trips = _round_trip_count(week_fills)
    checks: list[BandCheck] = []

    # 1. slippage vs modeled, +/-1 tick
    slippage = _mean_slippage_ticks(week_fills, costs)
    if slippage is None:
        checks.append(
            BandCheck(
                "mean_slippage_ticks",
                None,
                SLIPPAGE_BAND_TICKS,
                False,
                "no reference-priced fills this week — cannot verify slippage",
            )
        )
    else:
        observed, modeled = slippage
        deviation = abs(observed - modeled)
        checks.append(
            BandCheck(
                "mean_slippage_ticks",
                observed,
                modeled,
                deviation <= SLIPPAGE_BAND_TICKS,
                f"deviation {deviation:.2f} ticks (band +/-{SLIPPAGE_BAND_TICKS:.0f})",
            )
        )

    # 2. trade count, +/-20%
    low = expectations.expected_trades_per_week * (1 - TRADE_COUNT_BAND)
    high = expectations.expected_trades_per_week * (1 + TRADE_COUNT_BAND)
    checks.append(
        BandCheck(
            "round_trips",
            float(trips),
            expectations.expected_trades_per_week,
            low <= trips <= high,
            f"band [{low:.1f}, {high:.1f}]",
        )
    )

    # 3. realized vol in the target band
    vol = realized_annual_vol(week_snapshots)
    vol_low = expectations.annual_vol_target * expectations.vol_band_low
    vol_high = expectations.annual_vol_target * expectations.vol_band_high
    if vol is None:
        checks.append(
            BandCheck(
                "realized_annual_vol",
                None,
                expectations.annual_vol_target,
                False,
                "too few equity snapshots to estimate vol",
            )
        )
    else:
        checks.append(
            BandCheck(
                "realized_annual_vol",
                vol,
                expectations.annual_vol_target,
                vol_low <= vol <= vol_high,
                f"band [{vol_low:.3f}, {vol_high:.3f}]",
            )
        )

    # 4. cost per round trip, +/-25% (commissions from the statement + slippage cost)
    if trips == 0:
        checks.append(
            BandCheck(
                "cost_per_round_trip_cents",
                None,
                expectations.modeled_cost_per_round_trip_cents,
                False,
                "no round trips this week — cannot verify costs",
            )
        )
    else:
        commissions = sum(t.commission_cents for t in week_statement)
        slippage_cost = 0.0
        for fill in week_fills:
            if fill.reference_price is None:
                continue
            spec = costs.spec(fill.symbol)
            sign = 1 if fill.side == "buy" else -1
            adverse_ticks = sign * (fill.price - fill.reference_price) / spec.tick_size
            slippage_cost += adverse_ticks * spec.tick_value_cents * fill.quantity
        realized = (commissions + slippage_cost) / trips
        low_cost = expectations.modeled_cost_per_round_trip_cents * (1 - COST_BAND)
        high_cost = expectations.modeled_cost_per_round_trip_cents * (1 + COST_BAND)
        checks.append(
            BandCheck(
                "cost_per_round_trip_cents",
                realized,
                expectations.modeled_cost_per_round_trip_cents,
                low_cost <= realized <= high_cost,
                f"band [{low_cost:.0f}, {high_cost:.0f}] cents",
            )
        )

    return WeeklyReport(
        week_start=week_start,
        week_end=week_end,
        n_fills=len(week_fills),
        n_round_trips=trips,
        checks=checks,
    )
