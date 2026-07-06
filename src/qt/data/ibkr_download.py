"""IBKR historical downloader (BUILD_PLAN slice 4.1).

Design: everything testable is pure (pacing math, request planning, resume
logic); only :func:`download` touches ib_async, and it requires a running
IB Gateway/TWS with a paper login and active futures market data — an OWNER
item (§6) that is surfaced by a clear error, never faked.

Pacing (§1, hard IBKR limits, enforced as ceilings here):
- at most 60 historical requests per rolling 10 minutes,
- at most 6 requests per rolling 2 seconds for the same contract.
IBKR supplies ~2 years of history for expired futures — nothing older than 2y
past a contract's expiry is requested.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from qt.data.contracts import ContractMonth

BAR_SIZES = {"1 hour": "1hour", "1 day": "1day"}  # IBKR barSize -> filename tag
_HOURLY_CHUNK_DAYS = 28  # safe duration for 1-hour bars per request
_DAILY_CHUNK_DAYS = 360
_HISTORY_YEARS = 2


class DownloadError(Exception):
    """Downloader misconfiguration or broker-side failure."""


class PacingGate:
    """Rolling-window rate limiter with an injectable clock (unit-testable).

    ``wait_time`` returns how long to sleep before the next request is legal;
    ``record`` marks a request as sent. The caller owns the actual sleeping so
    the gate works under asyncio and in tests alike.
    """

    def __init__(
        self,
        max_per_window: int = 60,
        window_s: float = 600.0,
        max_per_contract: int = 6,
        contract_window_s: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_per_window < 1 or max_per_contract < 1:
            msg = "pacing limits must be >= 1"
            raise ValueError(msg)
        self._max_global = max_per_window
        self._window_s = window_s
        self._max_contract = max_per_contract
        self._contract_window_s = contract_window_s
        self._clock = clock
        self._global: deque[float] = deque()
        self._per_contract: dict[str, deque[float]] = {}

    def _prune(self, now: float) -> None:
        while self._global and now - self._global[0] >= self._window_s:
            self._global.popleft()
        for stamps in self._per_contract.values():
            while stamps and now - stamps[0] >= self._contract_window_s:
                stamps.popleft()

    def wait_time(self, contract_key: str) -> float:
        now = self._clock()
        self._prune(now)
        wait = 0.0
        if len(self._global) >= self._max_global:
            wait = max(wait, self._window_s - (now - self._global[0]))
        stamps = self._per_contract.get(contract_key)
        if stamps and len(stamps) >= self._max_contract:
            wait = max(wait, self._contract_window_s - (now - stamps[0]))
        return wait

    def record(self, contract_key: str) -> None:
        now = self._clock()
        self._prune(now)
        self._global.append(now)
        self._per_contract.setdefault(contract_key, deque()).append(now)


@dataclass(frozen=True)
class HistRequest:
    """One reqHistoricalData call: bars ending at ``end`` looking back ``duration_days``."""

    contract: ContractMonth
    bar_size: str  # IBKR barSize string, key of BAR_SIZES
    end: datetime  # UTC
    duration_days: int


def history_window(contract: ContractMonth, today: date) -> tuple[date, date]:
    """The [start, end] window IBKR can serve for this contract: from ~9 months
    before expiry (liquid life is shorter; extra is harmless) to expiry or
    today, whichever is earlier. Contracts expired more than 2y ago get an
    empty window (start > end) — IBKR keeps nothing older."""
    if today - timedelta(days=_HISTORY_YEARS * 365) > contract.expiry:
        return contract.expiry, contract.expiry - timedelta(days=1)  # empty
    end = min(contract.expiry, today)
    start = contract.expiry - timedelta(days=270)
    return start, end


def plan_requests(contract: ContractMonth, bar_size: str, today: date) -> list[HistRequest]:
    """Chunk a contract's history window into pacing-friendly requests,
    newest-last so a resumed run appends cleanly."""
    if bar_size not in BAR_SIZES:
        msg = f"unsupported bar size {bar_size!r}; expected one of {sorted(BAR_SIZES)}"
        raise DownloadError(msg)
    start, end = history_window(contract, today)
    if start > end:
        return []
    chunk_days = _HOURLY_CHUNK_DAYS if bar_size == "1 hour" else _DAILY_CHUNK_DAYS
    requests: list[HistRequest] = []
    chunk_end = datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC)
    span_start = datetime(start.year, start.month, start.day, tzinfo=UTC)
    while chunk_end > span_start:
        days = min(chunk_days, max(1, (chunk_end - span_start).days + 1))
        requests.append(
            HistRequest(contract=contract, bar_size=bar_size, end=chunk_end, duration_days=days)
        )
        chunk_end -= timedelta(days=days)
    requests.reverse()
    return requests


def raw_parquet_path(root: Path, contract: ContractMonth, bar_size: str) -> Path:
    """data/raw/ibkr/<symbol>/<contract>_<barsize>.parquet"""
    return root / "ibkr" / contract.symbol / f"{contract.contract_id}_{BAR_SIZES[bar_size]}.parquet"


def is_complete(path: Path) -> bool:
    """Resume marker: a non-empty parquet written by a finished contract pass.
    Partial passes write to a .tmp name first, so existence == completeness."""
    return path.is_file() and path.stat().st_size > 0


async def download(  # noqa: PLR0913 - connection params are owner-tunable
    contracts: list[ContractMonth],
    bar_sizes: list[str],
    raw_root: Path,
    host: str = "127.0.0.1",
    port: int = 4002,
    client_id: int = 17,
) -> list[Path]:
    """Download all planned history to raw parquet, pacing-aware and resumable.

    Requires IB Gateway/TWS with a paper login and market-data subscription
    (OWNER item, §6). Raises DownloadError with that context if unreachable.
    """
    import asyncio  # noqa: PLC0415 - keep pure helpers importable without an event loop

    from ib_async import IB, Contract  # noqa: PLC0415 - heavy import, gateway-only path

    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=10.0)
    except (TimeoutError, OSError) as exc:
        msg = (
            f"cannot reach IB Gateway at {host}:{port} — OWNER ACTION (§6): IBKR paper "
            "login + running Gateway + futures market-data subscription are required"
        )
        raise DownloadError(msg) from exc

    gate = PacingGate()
    written: list[Path] = []
    today = datetime.now(UTC).date()
    try:
        for contract_month in contracts:
            for bar_size in bar_sizes:
                target = raw_parquet_path(raw_root, contract_month, bar_size)
                if is_complete(target):
                    continue
                requests = plan_requests(contract_month, bar_size, today)
                if not requests:
                    continue
                frames: list[pl.DataFrame] = []
                ib_contract = Contract(
                    secType="FUT",
                    symbol=contract_month.symbol,
                    localSymbol=contract_month.local_symbol,
                    exchange="CME",
                    currency="USD",
                    includeExpired=True,
                )
                for request in requests:
                    wait = gate.wait_time(contract_month.contract_id)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    gate.record(contract_month.contract_id)
                    bars = await ib.reqHistoricalDataAsync(
                        ib_contract,
                        endDateTime=request.end,
                        durationStr=f"{request.duration_days} D",
                        barSizeSetting=request.bar_size,
                        whatToShow="TRADES",
                        useRTH=False,
                        formatDate=2,  # UTC
                    )
                    if bars:
                        frames.append(
                            pl.DataFrame(
                                {
                                    "ts": [b.date for b in bars],
                                    "open": [b.open for b in bars],
                                    "high": [b.high for b in bars],
                                    "low": [b.low for b in bars],
                                    "close": [b.close for b in bars],
                                    "volume": [float(b.volume) for b in bars],
                                }
                            )
                        )
                if not frames:
                    continue
                merged = pl.concat(frames).unique(subset="ts").sort("ts")
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".tmp")
                merged.write_parquet(tmp)
                tmp.replace(target)
                written.append(target)
    finally:
        ib.disconnect()
    return written
