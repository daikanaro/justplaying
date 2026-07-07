"""Roll-table builder (BUILD_PLAN §1 roll rule).

Rule: roll from front to next when the next contract's rolling 5-day volume
exceeds the front's; fallback: 5 business days before the front's expiry if
the volume crossover never happens. Rolls take effect at the close of the roll
date — the stitcher splices contracts after that session.

Business-day fallback uses plain weekday arithmetic (no holiday calendar):
a holiday-shifted fallback lands at most one session early, which is safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from typing import cast

import polars as pl

from qt.data.contracts import ContractMonth


class RollTableError(Exception):
    """Volume data is insufficient or inconsistent for roll construction."""


# A quarterly front is the liquid contract for ~one quarter. Crossovers seen
# earlier than this before its expiry happen while BOTH legs are thin
# far-from-front noise, not the §1 roll rule.
_CROSSOVER_WINDOW_DAYS = 100


@dataclass(frozen=True)
class Roll:
    """Switch from ``from_contract`` to ``to_contract`` after the close of ``date``."""

    date: date
    from_contract: str
    to_contract: str


def _business_days_before(day: date, n: int) -> date:
    out = day
    remaining = n
    while remaining > 0:
        out -= timedelta(days=1)
        if out.weekday() < 5:  # noqa: PLR2004 - 5 = Saturday
            remaining -= 1
    return out


def _rolling_volume(df: pl.DataFrame, lookback: int) -> pl.DataFrame:
    if df.is_empty() or set(df.columns) < {"date", "volume"}:
        msg = "volume frame must have non-empty 'date' and 'volume' columns"
        raise RollTableError(msg)
    return (
        df.sort("date")
        .with_columns(pl.col("volume").rolling_sum(window_size=lookback, min_samples=1).alias("v"))
        .select("date", "v")
    )


def build_roll_table(
    contracts: list[ContractMonth],
    daily_volumes: dict[str, pl.DataFrame],
    volume_lookback_days: int = 5,
    fallback_days_before_expiry: int = 5,
) -> list[Roll]:
    """Build the roll schedule for an expiry-ordered contract chain.

    ``daily_volumes`` maps contract_id -> DataFrame(date: pl.Date, volume: int)
    of that contract's daily volume.
    """
    if len(contracts) < 2:  # noqa: PLR2004 - a chain needs at least two contracts
        return []
    if sorted(contracts) != contracts:
        msg = "contracts must be ordered by expiry"
        raise RollTableError(msg)

    rolls: list[Roll] = []
    previous_roll: date | None = None
    for front, nxt in pairwise(contracts):
        for cid in (front.contract_id, nxt.contract_id):
            if cid not in daily_volumes:
                msg = f"no volume data for {cid}"
                raise RollTableError(msg)
        deadline = _business_days_before(front.expiry, fallback_days_before_expiry)
        front_v = _rolling_volume(daily_volumes[front.contract_id], volume_lookback_days)
        next_v = _rolling_volume(daily_volumes[nxt.contract_id], volume_lookback_days)
        joined = front_v.join(next_v, on="date", suffix="_next").sort("date")
        earliest = front.expiry - timedelta(days=_CROSSOVER_WINDOW_DAYS)
        if previous_roll is not None and previous_roll > earliest:
            earliest = previous_roll
        candidates = joined.filter(
            (pl.col("v_next") > pl.col("v"))
            & (pl.col("date") <= deadline)
            & (pl.col("date") > earliest)
        )
        roll_date = (
            deadline if candidates.is_empty() else cast("date", candidates.get_column("date").min())
        )
        if previous_roll is not None and roll_date <= previous_roll:
            msg = (
                f"roll {front.contract_id}->{nxt.contract_id} at {roll_date} does not "
                f"follow previous roll at {previous_roll}"
            )
            raise RollTableError(msg)
        rolls.append(Roll(roll_date, front.contract_id, nxt.contract_id))
        previous_roll = roll_date
    return rolls


def roll_table_frame(rolls: list[Roll]) -> pl.DataFrame:
    """Roll table as a DataFrame for persistence next to the curated series."""
    return pl.DataFrame(
        {
            "date": [r.date for r in rolls],
            "from_contract": [r.from_contract for r in rolls],
            "to_contract": [r.to_contract for r in rolls],
        }
    )
