"""Panama (difference) back-adjustment stitcher (BUILD_PLAN §1, locked decision).

Difference adjustment preserves point differences exactly, so $ P&L computed on
the continuous series equals $ P&L on the underlying contracts. The trade-offs
are documented in the plan: never compute long-horizon % returns on the
adjusted series without the roll table, and never use ratio adjustment.

Mechanics: the newest segment (current front contract) is left untouched. At
each roll (working backward) the offset ``close_new - close_old`` — both taken
at the two contracts' last common bar on the roll date — is added to every bar
of all older segments. The per-roll offsets are returned as an audit trail and
persisted next to the curated series.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from qt.data.roll_table import Roll
from qt.data.sessions import trading_day

PRICE_COLUMNS = ("open", "high", "low", "close")


def _with_session(bars: pl.DataFrame) -> pl.DataFrame:
    """Adds a ``session`` column: each bar's exchange TRADING day
    (qt.data.sessions.trading_day). Hourly bars after the 17:00-CT reopen
    belong to the NEXT session; splicing by UTC date would hand the roll
    evening's bars to the outgoing contract."""
    return bars.with_columns(
        pl.col("ts").map_elements(trading_day, return_dtype=pl.Date).alias("session")
    )


class StitchError(Exception):
    """Contract bars cannot be spliced into a continuous series."""


@dataclass(frozen=True)
class RollAdjustment:
    """Audit record: the offset applied to everything at/before this roll."""

    date: date
    from_contract: str
    to_contract: str
    offset: float


def _require_bars(bars: pl.DataFrame, contract_id: str) -> None:
    missing = {"ts", *PRICE_COLUMNS, "volume"} - set(bars.columns)
    if missing:
        msg = f"{contract_id}: bar frame missing columns {sorted(missing)}"
        raise StitchError(msg)
    if bars.is_empty():
        msg = f"{contract_id}: no bars"
        raise StitchError(msg)


def _roll_offset(old: pl.DataFrame, new: pl.DataFrame, roll: Roll) -> float:
    """Offset new-minus-old at the last bar timestamp both contracts share on
    (or before) the roll date. Both series must overlap there — a roll date
    with no common bar is a data defect, surfaced as StitchError."""
    old_on_date = _with_session(old).filter(pl.col("session") <= roll.date).drop("session")
    new_on_date = _with_session(new).filter(pl.col("session") <= roll.date).drop("session")
    common = old_on_date.join(new_on_date, on="ts", suffix="_new")
    if common.is_empty():
        msg = (
            f"roll {roll.from_contract}->{roll.to_contract} at {roll.date}: "
            "contracts share no bar at or before the roll date"
        )
        raise StitchError(msg)
    last = common.sort("ts").tail(1)
    return float(last.get_column("close_new")[0] - last.get_column("close")[0])


def stitch_panama(
    bars_by_contract: dict[str, pl.DataFrame],
    rolls: list[Roll],
) -> tuple[pl.DataFrame, list[RollAdjustment]]:
    """Splice per-contract bars into one Panama-adjusted continuous series.

    ``bars_by_contract`` maps contract_id -> DataFrame(ts: Datetime(UTC),
    open, high, low, close, volume). Works for daily and hourly bars alike;
    daily bars use a midnight-UTC timestamp.

    Returns (continuous frame with ``contract`` and ``adjustment`` columns,
    audit list ordered oldest roll first).
    """
    if not rolls:
        msg = "at least one roll is required; single-contract series need no stitching"
        raise StitchError(msg)
    chain = [rolls[0].from_contract, *(r.to_contract for r in rolls)]
    for cid in chain:
        if cid not in bars_by_contract:
            msg = f"roll table references {cid} but no bars were provided"
            raise StitchError(msg)
        _require_bars(bars_by_contract[cid], cid)

    # Segment boundaries: contract i owns SESSIONS (roll[i-1].date, roll[i].date].
    segments: list[pl.DataFrame] = []
    for i, cid in enumerate(chain):
        bars = _with_session(bars_by_contract[cid].sort("ts"))
        if i > 0:
            bars = bars.filter(pl.col("session") > rolls[i - 1].date)
        if i < len(rolls):
            bars = bars.filter(pl.col("session") <= rolls[i].date)
        bars = bars.drop("session")
        if bars.is_empty():
            msg = f"{cid}: no bars in its roll window"
            raise StitchError(msg)
        segments.append(bars.with_columns(pl.lit(cid).alias("contract")))

    # Offsets per roll, then cumulative adjustment per segment (newest = 0).
    offsets = [
        _roll_offset(bars_by_contract[r.from_contract], bars_by_contract[r.to_contract], r)
        for r in rolls
    ]
    adjustments = [float(sum(offsets[i:])) for i in range(len(chain))]

    adjusted_segments = [
        seg.with_columns(
            *[(pl.col(c) + adj).alias(c) for c in PRICE_COLUMNS],
            pl.lit(adj).alias("adjustment"),
        )
        for seg, adj in zip(segments, adjustments, strict=True)
    ]
    continuous = pl.concat(adjusted_segments).sort("ts")

    dup = continuous.filter(pl.col("ts").is_duplicated())
    if not dup.is_empty():
        msg = f"stitched series has {dup.height} duplicate timestamps across segments"
        raise StitchError(msg)

    audit = [
        RollAdjustment(r.date, r.from_contract, r.to_contract, off)
        for r, off in zip(rolls, offsets, strict=True)
    ]
    return continuous, audit
