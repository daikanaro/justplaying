"""IBKR downloader tests: pacing gate (fake clock), request planning, resume."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from qt.data.contracts import ContractMonth
from qt.data.ibkr_download import (
    DownloadError,
    PacingGate,
    history_window,
    is_complete,
    plan_requests,
    raw_parquet_path,
)

MESM24 = ContractMonth(2024, 6, "MES")


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_per_contract_limit() -> None:
    clock = FakeClock()
    gate = PacingGate(clock=clock)
    for _ in range(6):
        assert gate.wait_time("MESM2024") == 0.0
        gate.record("MESM2024")
    assert gate.wait_time("MESM2024") == pytest.approx(2.0)
    assert gate.wait_time("M2KM2024") == 0.0  # other contract unaffected
    clock.now = 2.0
    assert gate.wait_time("MESM2024") == 0.0


def test_global_limit() -> None:
    clock = FakeClock()
    gate = PacingGate(clock=clock)
    for i in range(60):
        clock.now = i * 0.01
        gate.record(f"C{i}")  # 60 different contracts: only the global cap binds
    clock.now = 1.0
    assert gate.wait_time("NEW") == pytest.approx(600.0 - 1.0)
    clock.now = 600.0
    assert gate.wait_time("NEW") == 0.0


def test_wait_time_is_max_of_both_limits() -> None:
    clock = FakeClock()
    gate = PacingGate(max_per_window=6, window_s=100.0, clock=clock)
    for _ in range(6):
        gate.record("X")  # trips BOTH the 6/2s per-contract and 6/100s global caps
    assert gate.wait_time("X") == pytest.approx(100.0)  # global dominates
    assert gate.wait_time("Y") == pytest.approx(100.0)


def test_invalid_limits_rejected() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        PacingGate(max_per_window=0)


def test_history_window_recent_contract() -> None:
    start, end = history_window(MESM24, today=date(2024, 5, 1))
    assert end == date(2024, 5, 1)  # still active: capped at today
    assert start == MESM24.expiry - timedelta(days=270)


def test_history_window_expired_contract() -> None:
    _start, end = history_window(MESM24, today=date(2024, 8, 1))
    assert end == MESM24.expiry  # expired: capped at expiry


def test_history_window_beyond_ibkr_retention_is_empty() -> None:
    start, end = history_window(MESM24, today=date(2026, 7, 6))
    assert start > end  # expiry 2024-06-21 is >2y before today: IBKR keeps nothing


def test_plan_requests_covers_window_and_is_chronological() -> None:
    requests = plan_requests(MESM24, "1 hour", today=date(2024, 5, 1))
    assert requests
    ends = [r.end for r in requests]
    assert ends == sorted(ends)
    span_start, span_end = history_window(MESM24, today=date(2024, 5, 1))
    earliest_covered = requests[0].end - timedelta(days=requests[0].duration_days)
    assert earliest_covered <= datetime(
        span_start.year, span_start.month, span_start.day, tzinfo=UTC
    )
    assert requests[-1].end.date() >= span_end
    assert all(r.duration_days <= 28 for r in requests)


def test_plan_requests_daily_single_chunk() -> None:
    requests = plan_requests(MESM24, "1 day", today=date(2024, 5, 1))
    assert len(requests) == 1
    assert requests[0].duration_days <= 360


def test_plan_requests_empty_for_ancient_contract() -> None:
    assert plan_requests(MESM24, "1 hour", today=date(2026, 7, 6)) == []


def test_plan_requests_rejects_unknown_bar_size() -> None:
    with pytest.raises(DownloadError, match="unsupported bar size"):
        plan_requests(MESM24, "5 mins", today=date(2024, 5, 1))


def test_raw_parquet_path_layout(tmp_path: Path) -> None:
    path = raw_parquet_path(tmp_path, MESM24, "1 hour")
    assert path == tmp_path / "ibkr" / "MES" / "MESM2024_1hour.parquet"


def test_is_complete_requires_non_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "x.parquet"
    assert not is_complete(path)
    path.touch()
    assert not is_complete(path)  # empty = interrupted, redo
    path.write_bytes(b"data")
    assert is_complete(path)
