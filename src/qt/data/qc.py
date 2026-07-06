"""Quality control for bar data (BUILD_PLAN slice 4.1).

Checks: session-calendar gap scan, duplicate timestamps, >N-sigma outlier
moves, zero-volume runs, and basic bar integrity. Criticals block promotion
from data/raw to data/curated — there is no override parameter on purpose.

Severity policy (documented, revisit against real data in this slice's QC
report): duplicates, integrity violations, outliers, and gaps on plain
weekdays are critical; gaps and zero-volume runs on/around holidays are
warnings (see qt.data.sessions for the holiday model).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

import polars as pl

from qt.data.sessions import expected_hourly_starts, is_holiday, trading_days

_OUTLIER_WINDOW = 100
_OUTLIER_MIN_SAMPLES = 30
_ZERO_VOLUME_CRITICAL_RUN = 3


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"


@dataclass(frozen=True)
class QCItem:
    severity: Severity
    check: str
    message: str


@dataclass
class QCReport:
    label: str
    n_bars: int
    items: list[QCItem] = field(default_factory=list)

    @property
    def criticals(self) -> list[QCItem]:
        return [i for i in self.items if i.severity is Severity.CRITICAL]

    @property
    def warnings(self) -> list[QCItem]:
        return [i for i in self.items if i.severity is Severity.WARNING]

    @property
    def is_clean(self) -> bool:
        """No criticals. Warnings do not block promotion."""
        return not self.criticals

    def to_text(self) -> str:
        lines = [
            f"QC report: {self.label} ({self.n_bars} bars) — "
            f"{len(self.criticals)} critical, {len(self.warnings)} warning"
        ]
        lines += [f"  [{i.severity.upper()}] {i.check}: {i.message}" for i in self.items]
        return "\n".join(lines)


class PromotionBlockedError(Exception):
    """Raised when promotion to curated/ is attempted with criticals present."""


def _require_columns(df: pl.DataFrame, label: str) -> None:
    missing = {"ts", "open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        msg = f"{label}: missing columns {sorted(missing)}"
        raise ValueError(msg)


def _check_duplicates(df: pl.DataFrame, report: QCReport) -> None:
    dups = df.filter(pl.col("ts").is_duplicated()).get_column("ts").unique().sort()
    if len(dups):
        report.items.append(
            QCItem(
                Severity.CRITICAL,
                "duplicates",
                f"{len(dups)} duplicated timestamps (first: {dups[0]})",
            )
        )


def _check_integrity(df: pl.DataFrame, report: QCReport) -> None:
    bad_range = df.filter(
        (pl.col("high") < pl.col("low"))
        | (pl.col("close") > pl.col("high"))
        | (pl.col("close") < pl.col("low"))
        | (pl.col("open") > pl.col("high"))
        | (pl.col("open") < pl.col("low"))
    )
    if bad_range.height:
        report.items.append(
            QCItem(
                Severity.CRITICAL,
                "bar_integrity",
                f"{bad_range.height} bars violate open/close within [low, high]",
            )
        )
    negative = df.filter(pl.col("volume") < 0)
    if negative.height:
        report.items.append(
            QCItem(Severity.CRITICAL, "bar_integrity", f"{negative.height} bars negative volume")
        )


def _check_outliers(df: pl.DataFrame, report: QCReport, sigma: float) -> None:
    """Close-to-close move vs the rolling stddev of PRIOR moves (shifted so an
    outlier cannot inflate its own yardstick). Note: works on price differences,
    which is the right space for a Panama-adjusted series (§1: no % returns)."""
    moves = df.sort("ts").with_columns(pl.col("close").diff().alias("move"))
    moves = moves.with_columns(
        pl.col("move")
        .rolling_std(window_size=_OUTLIER_WINDOW, min_samples=_OUTLIER_MIN_SAMPLES)
        .shift(1)
        .alias("scale")
    )
    flagged = moves.filter(
        pl.col("scale").is_not_null()
        & (pl.col("scale") > 0)
        & (pl.col("move").abs() > sigma * pl.col("scale"))
    )
    if flagged.height:
        first = flagged.get_column("ts")[0]
        report.items.append(
            QCItem(
                Severity.CRITICAL,
                "outliers",
                f"{flagged.height} moves exceed {sigma} sigma (first: {first})",
            )
        )


def _check_zero_volume_runs(df: pl.DataFrame, report: QCReport) -> None:
    ordered = df.sort("ts")
    run = 0
    run_start: datetime | None = None
    runs: list[tuple[datetime, int]] = []
    for ts, volume in zip(
        ordered.get_column("ts").to_list(), ordered.get_column("volume").to_list(), strict=True
    ):
        if volume == 0:
            if run == 0:
                run_start = ts
            run += 1
        else:
            if run and run_start is not None:
                runs.append((run_start, run))
            run = 0
    if run and run_start is not None:
        runs.append((run_start, run))
    for start_ts, length in runs:
        severity = (
            Severity.CRITICAL
            if length >= _ZERO_VOLUME_CRITICAL_RUN and not is_holiday(start_ts.date())
            else Severity.WARNING
        )
        report.items.append(
            QCItem(severity, "zero_volume", f"run of {length} zero-volume bars from {start_ts}")
        )


def _gap_items(missing_days: list[date], check: str) -> list[QCItem]:
    items = []
    for day in missing_days:
        severity = Severity.WARNING if is_holiday(day) else Severity.CRITICAL
        items.append(QCItem(severity, check, f"no bars on session date {day}"))
    return items


def qc_daily(df: pl.DataFrame, label: str, outlier_sigma: float) -> QCReport:
    """QC a daily bar frame (ts: Datetime UTC at midnight, OHLCV)."""
    _require_columns(df, label)
    report = QCReport(label=label, n_bars=df.height)
    if df.is_empty():
        report.items.append(QCItem(Severity.CRITICAL, "coverage", "no bars at all"))
        return report
    _check_duplicates(df, report)
    _check_integrity(df, report)
    _check_outliers(df, report, outlier_sigma)
    _check_zero_volume_runs(df, report)
    observed = set(df.get_column("ts").dt.date().to_list())
    span_start, span_end = min(observed), max(observed)
    missing = [d for d in trading_days(span_start, span_end) if d not in observed]
    report.items.extend(_gap_items(missing, "daily_gaps"))
    return report


def qc_hourly(df: pl.DataFrame, label: str, outlier_sigma: float) -> QCReport:
    """QC an hourly bar frame (ts: Datetime UTC = bar start, OHLCV)."""
    _require_columns(df, label)
    report = QCReport(label=label, n_bars=df.height)
    if df.is_empty():
        report.items.append(QCItem(Severity.CRITICAL, "coverage", "no bars at all"))
        return report
    _check_duplicates(df, report)
    _check_integrity(df, report)
    _check_outliers(df, report, outlier_sigma)
    _check_zero_volume_runs(df, report)
    observed = set(df.get_column("ts").to_list())
    dates = df.get_column("ts").dt.date()
    missing_by_day: dict[date, int] = {}
    for expected in expected_hourly_starts(dates.min(), dates.max()):  # type: ignore[arg-type]
        if expected not in observed:
            missing_by_day[expected.date()] = missing_by_day.get(expected.date(), 0) + 1
    for day, count in sorted(missing_by_day.items()):
        severity = Severity.WARNING if is_holiday(day) else Severity.CRITICAL
        report.items.append(
            QCItem(severity, "hourly_gaps", f"{count} expected hourly bars missing on {day}")
        )
    return report


def promote(raw_path: Path, curated_path: Path, report: QCReport) -> None:
    """Copy a raw artifact to curated/. Criticals block promotion, always."""
    if not report.is_clean:
        msg = (
            f"promotion of {raw_path} blocked: {len(report.criticals)} critical QC items\n"
            + report.to_text()
        )
        raise PromotionBlockedError(msg)
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, curated_path)
