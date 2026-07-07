"""CME Globex session calendar for equity index futures (MES, M2K).

This is the ONE module where exchange-local time exists; everything it returns
is UTC. Session template (America/Chicago):

- Opens Sunday 17:00, closes Friday 16:00.
- Daily maintenance halt 16:00-17:00 Mon-Thu.

Holidays: we deliberately do NOT encode CME's per-holiday early-close minutiae.
:func:`holiday_dates` returns US market holidays (full or partial); the QC gap
scan treats missing bars on those dates as warnings instead of criticals. A
missing bar on a plain weekday stays critical.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")

_HALT_START = time(16, 0)  # daily maintenance + Friday close, exchange time
_HALT_END = time(17, 0)  # daily reopen + Sunday open, exchange time

_SATURDAY = 5
_SUNDAY = 6
_FRIDAY = 4


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) given weekday of a month; weekday 0=Monday."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)  # noqa: PLR2004
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def _observed(holiday: date) -> date:
    """US observance: Sunday holidays roll to Monday; Saturday to Friday."""
    if holiday.weekday() == _SUNDAY:
        return holiday + timedelta(days=1)
    if holiday.weekday() == _SATURDAY:
        return holiday - timedelta(days=1)
    return holiday


def holiday_dates(year: int) -> frozenset[date]:
    """US market holidays (full closes and partial/early-close days alike)."""
    good_friday = easter_sunday(year) - timedelta(days=2)
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    days = {
        _observed(date(year, 1, 1)),  # New Year's Day
        _nth_weekday(year, 1, 0, 3),  # MLK Day
        _nth_weekday(year, 2, 0, 3),  # Presidents' Day
        good_friday,
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        thanksgiving,
        thanksgiving + timedelta(days=1),  # early-close Friday
        _observed(date(year, 12, 25)),  # Christmas
    }
    # Recurring CME early-close days adjacent to full holidays (when weekdays).
    for early in (date(year, 7, 3), date(year, 12, 24)):
        if early.weekday() < _SATURDAY:
            days.add(early)
    return frozenset(days)


def is_holiday(day: date) -> bool:
    return day in holiday_dates(day.year)


def is_open(ts_utc: datetime) -> bool:
    """True if Globex equity futures trade at this UTC instant (template only,
    holidays not considered — see module docstring)."""
    if ts_utc.tzinfo is None:
        msg = "is_open requires a timezone-aware UTC datetime"
        raise ValueError(msg)
    local = ts_utc.astimezone(CHICAGO)
    weekday, t = local.weekday(), local.time()
    if weekday == _SATURDAY:
        return False
    if weekday == _SUNDAY:
        return t >= _HALT_END
    if weekday == _FRIDAY:
        return t < _HALT_START
    return t < _HALT_START or t >= _HALT_END


_RTH_START = time(8, 30)  # US equity cash session, exchange (Chicago) time
_RTH_END = time(15, 0)


def trading_day(ts_utc: datetime) -> date:
    """The Globex TRADING day a UTC instant belongs to: sessions open at
    17:00 Chicago the prior evening, so anything at/after 17:00 CT belongs to
    the NEXT weekday's session. This is the date the daily loss halt, roll
    splices, and holiday classification should key on — not the UTC date."""
    if ts_utc.tzinfo is None:
        msg = "trading_day requires a timezone-aware UTC datetime"
        raise ValueError(msg)
    local = ts_utc.astimezone(CHICAGO)
    day = local.date()
    if local.time() >= _HALT_END:  # evening session: belongs to tomorrow
        day += timedelta(days=1)
    while day.weekday() >= _SATURDAY:
        day += timedelta(days=1)
    return day


def is_rth(ts_utc: datetime) -> bool:
    """True during the US equity cash session (08:30-15:00 Chicago, Mon-Fri).
    The cost model charges 1 tick slippage here, 2 ticks elsewhere (§1)."""
    if ts_utc.tzinfo is None:
        msg = "is_rth requires a timezone-aware UTC datetime"
        raise ValueError(msg)
    local = ts_utc.astimezone(CHICAGO)
    return local.weekday() < _SATURDAY and _RTH_START <= local.time() < _RTH_END


def expected_hourly_starts(start: date, end: date) -> list[datetime]:
    """UTC start times of every hourly bar the session template expects in
    [start, end] (dates inclusive, interpreted as UTC calendar days)."""
    if end < start:
        msg = f"end {end} before start {start}"
        raise ValueError(msg)
    out: list[datetime] = []
    cursor = datetime(start.year, start.month, start.day, tzinfo=UTC)
    stop = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
    while cursor < stop:
        if is_open(cursor):
            out.append(cursor)
        cursor += timedelta(hours=1)
    return out


def trading_days(start: date, end: date) -> list[date]:
    """Weekday session dates in [start, end], holidays included (the QC layer
    downgrades holiday gaps to warnings rather than excluding the dates)."""
    if end < start:
        msg = f"end {end} before start {start}"
        raise ValueError(msg)
    out: list[date] = []
    day = start
    while day <= end:
        if day.weekday() < _SATURDAY:
            out.append(day)
        day += timedelta(days=1)
    return out
