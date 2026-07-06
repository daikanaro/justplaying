"""QC tests: every defect class flags at the right severity; criticals block
promotion with no override path."""

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from qt.data.qc import PromotionBlockedError, Severity, promote, qc_daily, qc_hourly
from qt.data.sessions import expected_hourly_starts, trading_days

SIGMA = 12.0


def frame(
    ts: list[datetime], closes: list[float], volumes: list[float] | None = None
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": ts,
            "open": closes,
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
            "volume": volumes if volumes is not None else [100.0] * len(ts),
        }
    ).with_columns(pl.col("ts").dt.replace_time_zone("UTC"))


def daily_frame(days: list[date], closes: list[float] | None = None) -> pl.DataFrame:
    ts = [datetime(d.year, d.month, d.day, tzinfo=UTC) for d in days]
    if closes is None:
        closes = [100.0 + 0.1 * (i % 2) for i in range(len(days))]  # gentle wiggle
    return frame(ts, closes)


def test_clean_daily_frame_is_clean() -> None:
    days = trading_days(date(2024, 7, 8), date(2024, 7, 19))  # no holidays in range
    report = qc_daily(daily_frame(days), "clean", SIGMA)
    assert report.is_clean
    assert report.items == []


def test_duplicate_timestamps_critical() -> None:
    days = trading_days(date(2024, 7, 8), date(2024, 7, 12))
    df = daily_frame([*days, days[2]])
    report = qc_daily(df, "dups", SIGMA)
    assert any(i.check == "duplicates" and i.severity is Severity.CRITICAL for i in report.items)


def test_weekday_gap_critical_holiday_gap_warning() -> None:
    # Range spans July 4 2024 (holiday, Thursday). Drop the holiday AND a
    # plain Wednesday: holiday gap -> warning, weekday gap -> critical.
    days = [
        d
        for d in trading_days(date(2024, 7, 1), date(2024, 7, 12))
        if d not in (date(2024, 7, 4), date(2024, 7, 10))
    ]
    report = qc_daily(daily_frame(days), "gaps", SIGMA)
    gaps = {i.message: i.severity for i in report.items if i.check == "daily_gaps"}
    assert gaps["no bars on session date 2024-07-04"] is Severity.WARNING
    assert gaps["no bars on session date 2024-07-10"] is Severity.CRITICAL


def test_outlier_move_critical() -> None:
    days = trading_days(date(2024, 1, 8), date(2024, 5, 31))
    closes = [100.0 + 0.1 * (i % 2) for i in range(len(days))]
    closes[-1] = 150.0  # a 50-point jump against ~0.1 wiggle
    report = qc_daily(daily_frame(days, closes), "outlier", SIGMA)
    assert any(i.check == "outliers" and i.severity is Severity.CRITICAL for i in report.items)


def test_zero_volume_run_severities() -> None:
    days = trading_days(date(2024, 7, 8), date(2024, 7, 19))
    volumes = [100.0] * len(days)
    volumes[1] = 0.0  # single zero -> warning
    volumes[5] = volumes[6] = volumes[7] = 0.0  # run of 3 on plain weekdays -> critical
    ts = [datetime(d.year, d.month, d.day, tzinfo=UTC) for d in days]
    closes = [100.0 + 0.1 * (i % 2) for i in range(len(days))]
    report = qc_daily(frame(ts, closes, volumes), "zerovol", SIGMA)
    zero_items = [i for i in report.items if i.check == "zero_volume"]
    assert {i.severity for i in zero_items} == {Severity.WARNING, Severity.CRITICAL}


def test_bar_integrity_critical() -> None:
    days = trading_days(date(2024, 7, 8), date(2024, 7, 12))
    df = daily_frame(days).with_columns(
        pl.when(pl.int_range(pl.len()) == 2)
        .then(pl.col("low") + 50.0)  # low far above high
        .otherwise(pl.col("low"))
        .alias("low")
    )
    report = qc_daily(df, "integrity", SIGMA)
    assert any(i.check == "bar_integrity" for i in report.criticals)


def test_empty_frame_critical() -> None:
    df = daily_frame(trading_days(date(2024, 7, 8), date(2024, 7, 9))).head(0)
    report = qc_daily(df, "empty", SIGMA)
    assert not report.is_clean


def test_hourly_gaps_counted_per_day() -> None:
    starts = expected_hourly_starts(date(2024, 7, 8), date(2024, 7, 9))
    kept = [t for t in starts if t not in (starts[3], starts[4])]
    closes = [100.0 + 0.01 * (i % 2) for i in range(len(kept))]
    report = qc_hourly(frame(kept, closes), "hourly", SIGMA)
    gap_items = [i for i in report.items if i.check == "hourly_gaps"]
    assert len(gap_items) == 1
    assert "2 expected hourly bars missing" in gap_items[0].message
    assert gap_items[0].severity is Severity.CRITICAL


def test_hourly_complete_session_is_clean() -> None:
    starts = expected_hourly_starts(date(2024, 7, 8), date(2024, 7, 9))
    closes = [100.0 + 0.01 * (i % 2) for i in range(len(starts))]
    report = qc_hourly(frame(starts, closes), "hourly-clean", SIGMA)
    assert report.is_clean


def test_promotion_blocked_on_criticals(tmp_path: Path) -> None:
    raw = tmp_path / "raw.parquet"
    curated = tmp_path / "curated" / "raw.parquet"
    days = trading_days(date(2024, 7, 8), date(2024, 7, 12))
    daily_frame([*days, days[0]]).write_parquet(raw)  # duplicate -> critical
    report = qc_daily(pl.read_parquet(raw), "promo", SIGMA)
    with pytest.raises(PromotionBlockedError, match="blocked"):
        promote(raw, curated, report)
    assert not curated.exists()


def test_promotion_copies_when_clean(tmp_path: Path) -> None:
    raw = tmp_path / "raw.parquet"
    curated = tmp_path / "curated" / "raw.parquet"
    days = trading_days(date(2024, 7, 8), date(2024, 7, 12))
    daily_frame(days).write_parquet(raw)
    report = qc_daily(pl.read_parquet(raw), "promo", SIGMA)
    promote(raw, curated, report)
    assert curated.is_file()
    assert pl.read_parquet(curated).height == len(days)
