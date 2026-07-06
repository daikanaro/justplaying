"""Events-calendar loader/validator tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.data.events import Event, EventsError, in_blackout, load_events


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "events.csv"
    path.write_text(body, encoding="utf-8")
    return path


VALID = "datetime_utc,type\n2026-07-15T18:00:00Z,FOMC\n2026-08-01T12:30:00+00:00,NFP\n"


def test_valid_calendar_loads(tmp_path: Path) -> None:
    events = load_events(write(tmp_path, VALID))
    assert events == [
        Event(datetime(2026, 7, 15, 18, 0, tzinfo=UTC), "FOMC"),
        Event(datetime(2026, 8, 1, 12, 30, tzinfo=UTC), "NFP"),
    ]


def test_header_only_is_valid_and_empty(tmp_path: Path) -> None:
    assert load_events(write(tmp_path, "datetime_utc,type\n")) == []


def test_shipped_placeholder_loads() -> None:
    repo_calendar = Path(__file__).resolve().parent.parent / "data" / "calendar" / "events.csv"
    assert load_events(repo_calendar) == []


def test_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(EventsError, match="not found"):
        load_events(tmp_path / "events.csv")


@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("wrong header", "when,what\n2026-07-15T18:00:00Z,FOMC\n"),
        ("naive timestamp", "datetime_utc,type\n2026-07-15T18:00:00,FOMC\n"),
        ("non-utc offset", "datetime_utc,type\n2026-07-15T18:00:00+03:00,FOMC\n"),
        ("unparseable timestamp", "datetime_utc,type\nnext tuesday,FOMC\n"),
        ("lowercase type", "datetime_utc,type\n2026-07-15T18:00:00Z,fomc\n"),
        ("empty type", "datetime_utc,type\n2026-07-15T18:00:00Z,\n"),
        ("extra column", "datetime_utc,type\n2026-07-15T18:00:00Z,FOMC,high\n"),
        (
            "unsorted",
            "datetime_utc,type\n2026-08-01T12:30:00Z,NFP\n2026-07-15T18:00:00Z,FOMC\n",
        ),
        (
            "duplicate",
            "datetime_utc,type\n2026-07-15T18:00:00Z,FOMC\n2026-07-15T18:00:00Z,FOMC\n",
        ),
        ("empty file", ""),
    ],
)
def test_invalid_calendars_rejected(tmp_path: Path, label: str, body: str) -> None:
    with pytest.raises(EventsError):
        load_events(write(tmp_path, body))


def test_blank_lines_tolerated(tmp_path: Path) -> None:
    events = load_events(write(tmp_path, "datetime_utc,type\n\n2026-07-15T18:00:00Z,CPI\n\n"))
    assert len(events) == 1


def test_in_blackout_window() -> None:
    events = [Event(datetime(2026, 7, 15, 18, 0, tzinfo=UTC), "FOMC")]
    assert in_blackout(datetime(2026, 7, 15, 17, 30, tzinfo=UTC), events, 30)  # edge: exactly 30m
    assert in_blackout(datetime(2026, 7, 15, 18, 29, tzinfo=UTC), events, 30)
    assert not in_blackout(datetime(2026, 7, 15, 17, 29, tzinfo=UTC), events, 30)
    assert not in_blackout(datetime(2026, 7, 15, 18, 31, tzinfo=UTC), events, 30)


def test_in_blackout_rejects_naive() -> None:
    with pytest.raises(ValueError, match="aware"):
        in_blackout(datetime(2026, 7, 15, 18, 0), [], 30)
