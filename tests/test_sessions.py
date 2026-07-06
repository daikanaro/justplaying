"""Session-calendar tests: holidays, open/closed instants, expected bars."""

from datetime import UTC, date, datetime

import pytest

from qt.data.sessions import (
    easter_sunday,
    expected_hourly_starts,
    holiday_dates,
    is_holiday,
    is_open,
    trading_days,
)


def test_known_holidays_2024() -> None:
    days = holiday_dates(2024)
    assert date(2024, 1, 1) in days  # New Year's
    assert date(2024, 1, 15) in days  # MLK (3rd Monday)
    assert date(2024, 3, 29) in days  # Good Friday
    assert date(2024, 7, 4) in days  # Independence Day (Thursday)
    assert date(2024, 11, 28) in days  # Thanksgiving
    assert date(2024, 11, 29) in days  # Friday after
    assert date(2024, 12, 25) in days  # Christmas
    assert date(2024, 7, 8) not in days


def test_observed_shifts() -> None:
    # July 4 2026 is a Saturday -> observed Friday July 3.
    assert date(2026, 7, 3) in holiday_dates(2026)
    # Juneteenth 2022 was a Sunday -> observed Monday June 20.
    assert date(2022, 6, 20) in holiday_dates(2022)


def test_easter_known_dates() -> None:
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)


@pytest.mark.parametrize(
    ("ts", "open_"),
    [
        (datetime(2024, 7, 8, 14, 0, tzinfo=UTC), True),  # Monday 09:00 CT
        (datetime(2024, 7, 8, 21, 30, tzinfo=UTC), False),  # Monday 16:30 CT halt
        (datetime(2024, 7, 8, 22, 0, tzinfo=UTC), True),  # Monday 17:00 CT reopen
        (datetime(2024, 7, 6, 14, 0, tzinfo=UTC), False),  # Saturday
        (datetime(2024, 7, 7, 21, 59, tzinfo=UTC), False),  # Sunday 16:59 CT
        (datetime(2024, 7, 7, 22, 0, tzinfo=UTC), True),  # Sunday 17:00 CT open
        (datetime(2024, 7, 5, 20, 59, tzinfo=UTC), True),  # Friday 15:59 CT
        (datetime(2024, 7, 5, 21, 0, tzinfo=UTC), False),  # Friday 16:00 CT close
        (datetime(2024, 1, 8, 22, 30, tzinfo=UTC), False),  # CST winter: 16:30 CT halt
    ],
)
def test_is_open(ts: datetime, open_: bool) -> None:
    assert is_open(ts) is open_


def test_is_open_rejects_naive() -> None:
    with pytest.raises(ValueError, match="aware"):
        is_open(datetime(2024, 7, 8, 14, 0))


def test_expected_hourly_starts_regular_monday() -> None:
    # A regular UTC Monday in CDT: only the 16:00-17:00 CT halt hour is closed.
    starts = expected_hourly_starts(date(2024, 7, 8), date(2024, 7, 8))
    assert len(starts) == 23
    assert datetime(2024, 7, 8, 21, 0, tzinfo=UTC) not in starts


def test_expected_hourly_starts_saturday_empty() -> None:
    # UTC Saturday: 00:00-21:59 UTC is Friday-evening-after-close/Saturday CT.
    starts = expected_hourly_starts(date(2024, 7, 6), date(2024, 7, 6))
    assert starts == []


def test_trading_days_excludes_weekends_keeps_holidays() -> None:
    days = trading_days(date(2024, 7, 1), date(2024, 7, 7))
    assert date(2024, 7, 6) not in days  # Saturday
    assert date(2024, 7, 4) in days  # holiday stays; QC downgrades it
    assert is_holiday(date(2024, 7, 4))
    assert len(days) == 5
