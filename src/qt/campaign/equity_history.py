"""Daily equity snapshots (JSONL) + realized-volatility math for the weekly
vol band. The engine/watchdog appends one snapshot per session close."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path

TRADING_DAYS_PER_YEAR = 252.0
_MIN_RETURNS_FOR_VOL = 3


@dataclass(frozen=True)
class EquitySnapshot:
    day: date
    equity_cents: int


def append_snapshot(path: Path, snapshot: EquitySnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps({"day": snapshot.day.isoformat(), "equity_cents": snapshot.equity_cents})
            + "\n"
        )


def load_snapshots(path: Path) -> list[EquitySnapshot]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        out.append(EquitySnapshot(date.fromisoformat(raw["day"]), int(raw["equity_cents"])))
    return sorted(out, key=lambda s: s.day)


def realized_annual_vol(snapshots: list[EquitySnapshot]) -> float | None:
    """Annualized stddev of daily simple returns; None below the minimum
    sample (a vol estimate from two points is noise, not a band check)."""
    returns = [
        (b.equity_cents - a.equity_cents) / a.equity_cents
        for a, b in pairwise(snapshots)
        if a.equity_cents > 0
    ]
    if len(returns) < _MIN_RETURNS_FOR_VOL:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)
