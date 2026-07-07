"""The campaign clock (§4.7 acceptance): >= 4 CONSECUTIVE weekly reports
inside all bands. An out-of-band week resets the clock — diagnose, fix,
restart. So does a calendar gap between recorded weeks: an unreported week is
an unmonitored week, not an in-band one. State persists as JSON so the clock
survives restarts; weeks are append-only (recording an older or duplicate
week is an error, not a rewrite).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from qt.campaign.weekly import WeeklyReport

REQUIRED_CONSECUTIVE_WEEKS = 4

# Largest seam between one week's end and the next week's start that still
# counts as consecutive: 1 day for Mon..Sun windows, 3 for Mon..Fri.
_MAX_WEEK_SEAM = timedelta(days=3)


class CampaignError(Exception):
    """Weeks recorded out of order or twice — the clock cannot be gamed."""


@dataclass(frozen=True)
class CampaignStatus:
    consecutive_in_band: int
    total_weeks: int
    eligible_for_go_nogo: bool
    last_week_end: str | None


class CampaignTracker:
    def __init__(self, state_path: Path) -> None:
        self._path = state_path
        if state_path.is_file():
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            self._weeks: list[dict[str, str | bool]] = list(raw["weeks"])
        else:
            self._weeks = []

    def record_week(self, report: WeeklyReport) -> CampaignStatus:
        last_end = self._last_week_end()
        if last_end is not None and report.week_start <= last_end:
            msg = (
                f"week starting {report.week_start} overlaps or precedes the last "
                f"recorded week ending {last_end} — weeks are append-only"
            )
            raise CampaignError(msg)
        self._weeks.append(
            {
                "week_start": report.week_start.isoformat(),
                "week_end": report.week_end.isoformat(),
                "inside_all_bands": report.inside_all_bands,
            }
        )
        self._save()
        return self.status()

    def status(self) -> CampaignStatus:
        consecutive = 0
        next_start: date | None = None
        for week in reversed(self._weeks):
            if not week["inside_all_bands"]:
                break
            week_end = date.fromisoformat(str(week["week_end"]))
            if next_start is not None and next_start - week_end > _MAX_WEEK_SEAM:
                break  # calendar gap: the streak cannot span an unmonitored week
            consecutive += 1
            next_start = date.fromisoformat(str(week["week_start"]))
        last = self._weeks[-1]["week_end"] if self._weeks else None
        return CampaignStatus(
            consecutive_in_band=consecutive,
            total_weeks=len(self._weeks),
            eligible_for_go_nogo=consecutive >= REQUIRED_CONSECUTIVE_WEEKS,
            last_week_end=str(last) if last is not None else None,
        )

    def _last_week_end(self) -> date | None:
        if not self._weeks:
            return None
        return date.fromisoformat(str(self._weeks[-1]["week_end"]))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"weeks": self._weeks}, indent=2) + "\n", encoding="utf-8")
