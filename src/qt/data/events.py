"""Economic events calendar loader/validator (BUILD_PLAN §1).

``data/calendar/events.csv`` is owner-maintained: header ``datetime_utc,type``,
one row per event (FOMC statement, CPI, NFP, ...). Timestamps must carry an
explicit UTC marker ("Z" or "+00:00") — naive timestamps are rejected rather
than assumed, because a silently misread event time defeats the blackout.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TYPE_RE = re.compile(r"[A-Z0-9_]{2,24}")
_HEADER = ["datetime_utc", "type"]


class EventsError(Exception):
    """events.csv is missing, malformed, or inconsistent. Fatal at startup."""


@dataclass(frozen=True, order=True)
class Event:
    ts_utc: datetime
    type: str


def load_events(path: Path) -> list[Event]:
    """Load and validate the calendar. An empty calendar (header only) is valid
    but the caller should surface it — the owner populates it monthly (§6)."""
    if not path.is_file():
        msg = f"events calendar not found: {path}"
        raise EventsError(msg)
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            msg = f"{path}: empty file, expected header {_HEADER}"
            raise EventsError(msg) from None
        if [h.strip() for h in header] != _HEADER:
            msg = f"{path}: header {header} != {_HEADER}"
            raise EventsError(msg)
        events: list[Event] = []
        for lineno, row in enumerate(reader, start=2):
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            if len(row) != len(_HEADER):
                msg = f"{path}:{lineno}: expected 2 columns, got {len(row)}"
                raise EventsError(msg)
            raw_ts, raw_type = row[0].strip(), row[1].strip()
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError as exc:
                msg = f"{path}:{lineno}: unparseable datetime {raw_ts!r}"
                raise EventsError(msg) from exc
            if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
                msg = f"{path}:{lineno}: {raw_ts!r} must be explicit UTC ('Z' or '+00:00')"
                raise EventsError(msg)
            if not _TYPE_RE.fullmatch(raw_type):
                msg = f"{path}:{lineno}: invalid event type {raw_type!r}"
                raise EventsError(msg)
            events.append(Event(ts.astimezone(UTC), raw_type))
    if events != sorted(events):
        msg = f"{path}: events must be sorted by datetime_utc"
        raise EventsError(msg)
    seen: set[Event] = set()
    for event in events:
        if event in seen:
            msg = f"{path}: duplicate event {event.type} at {event.ts_utc.isoformat()}"
            raise EventsError(msg)
        seen.add(event)
    return events


def in_blackout(ts_utc: datetime, events: list[Event], blackout_min: int) -> bool:
    """True if ``ts_utc`` falls within ±blackout_min minutes of any event (§2)."""
    if ts_utc.tzinfo is None:
        msg = "in_blackout requires a timezone-aware datetime"
        raise ValueError(msg)
    window = timedelta(minutes=blackout_min)
    return any(abs(ts_utc - e.ts_utc) <= window for e in events)
