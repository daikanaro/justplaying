"""Binance perpetual funding-rate history — the only S3 deliverable in Phase 4.

Public REST (/fapi/v1/fundingRate), read-only, no keys, production endpoint.
Produces the three §3 S3 statistics:

(a) fraction of funding intervals pinned at exactly +0.01% (the default rate —
    a high pinned fraction means the "carry" is mostly the exchange default,
    not a market signal),
(b) rolling 30-day annualized funding,
(c) longest streak of consecutive negative-funding intervals,

plus a three-panel plot of all of them. If the endpoint is geo-blocked from
the machine running this, that fact is recorded (GeoBlockedError) — per spec,
never worked around.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import polars as pl

_PAGE_LIMIT = 1000
_PINNED_RATE = Decimal("0.0001")  # +0.01% per 8h interval
_INTERVALS_PER_DAY = 3
_ANNUALIZATION_DAYS = 365
_ROLLING_DAYS = 30
_GEO_BLOCK_STATUSES = {403, 451}


class FundingError(Exception):
    """Download or validation failed."""


class GeoBlockedError(FundingError):
    """The endpoint refused this location. Record the fact; do not work around."""


@dataclass(frozen=True)
class NegativeStreak:
    intervals: int
    start: str  # ISO timestamps (JSON-friendly)
    end: str


@dataclass(frozen=True)
class FundingStats:
    symbol: str
    n_intervals: int
    first_interval: str
    last_interval: str
    pinned_rate: str
    pinned_fraction: float
    mean_annualized: float
    longest_negative_streak: NegativeStreak | None


def fetch_funding_history(
    base_url: str,
    symbol: str,
    start: datetime,
    client: httpx.Client,
    end: datetime | None = None,
) -> pl.DataFrame:
    """Page through /fapi/v1/fundingRate from ``start`` (UTC) to ``end``/now.

    Returns (ts: Datetime UTC, rate: Float64, rate_str: exact decimal string).
    The exact string is kept because statistic (a) is an EXACT comparison and
    float round-trips would blur it.
    """
    if start.tzinfo is None or (end is not None and end.tzinfo is None):
        msg = "start/end must be timezone-aware"
        raise FundingError(msg)
    rows: list[dict[str, Any]] = []
    cursor_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000) if end else None
    while True:
        params: dict[str, str | int] = {
            "symbol": symbol,
            "startTime": cursor_ms,
            "limit": _PAGE_LIMIT,
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        try:
            response = client.get(f"{base_url}/fapi/v1/fundingRate", params=params)
        except httpx.HTTPError as exc:
            msg = f"funding request failed: {exc}"
            raise FundingError(msg) from exc
        if response.status_code in _GEO_BLOCK_STATUSES:
            msg = (
                f"{base_url} returned HTTP {response.status_code} — endpoint is "
                "geo-blocked from this machine; recording the fact per §3 S3"
            )
            raise GeoBlockedError(msg)
        if response.status_code != httpx.codes.OK:
            msg = f"funding request HTTP {response.status_code}: {response.text[:200]}"
            raise FundingError(msg)
        batch = response.json()
        if not isinstance(batch, list):
            msg = f"unexpected funding payload: {str(batch)[:200]}"
            raise FundingError(msg)
        rows.extend(batch)
        if len(batch) < _PAGE_LIMIT:
            break
        cursor_ms = int(batch[-1]["fundingTime"]) + 1
    if not rows:
        msg = f"no funding intervals returned for {symbol} since {start.isoformat()}"
        raise FundingError(msg)
    df = pl.DataFrame(
        {
            "ts": [datetime.fromtimestamp(int(r["fundingTime"]) / 1000, tz=UTC) for r in rows],
            "rate": [float(r["fundingRate"]) for r in rows],
            "rate_str": [str(r["fundingRate"]) for r in rows],
        }
    ).sort("ts")
    if df.get_column("ts").is_duplicated().any():
        msg = "funding history has duplicate interval timestamps"
        raise FundingError(msg)
    return df


def rolling_annualized(df: pl.DataFrame, days: int = _ROLLING_DAYS) -> pl.DataFrame:
    """Rolling ``days``-day sum of funding, annualized (fraction/year)."""
    return (
        df.sort("ts")
        .rolling(index_column="ts", period=f"{days}d")
        .agg(pl.col("rate").sum().alias("window_sum"))
        .with_columns((pl.col("window_sum") * (_ANNUALIZATION_DAYS / days)).alias("annualized"))
        .select("ts", "annualized")
    )


def longest_negative_streak(df: pl.DataFrame) -> NegativeStreak | None:
    ordered = df.sort("ts")
    best: tuple[int, datetime, datetime] | None = None
    run_start: datetime | None = None
    run = 0
    for ts, rate in zip(
        ordered.get_column("ts").to_list(), ordered.get_column("rate").to_list(), strict=True
    ):
        if rate < 0:
            if run == 0:
                run_start = ts
            run += 1
            if run_start is not None and (best is None or run > best[0]):
                best = (run, run_start, ts)
        else:
            run = 0
    if best is None:
        return None
    return NegativeStreak(best[0], best[1].isoformat(), best[2].isoformat())


def compute_stats(df: pl.DataFrame, symbol: str) -> FundingStats:
    pinned = sum(1 for s in df.get_column("rate_str").to_list() if Decimal(s) == _PINNED_RATE)
    mean_rate = float(df.get_column("rate").mean())  # type: ignore[arg-type]
    return FundingStats(
        symbol=symbol,
        n_intervals=df.height,
        first_interval=df.get_column("ts").min().isoformat(),  # type: ignore[union-attr]
        last_interval=df.get_column("ts").max().isoformat(),  # type: ignore[union-attr]
        pinned_rate=str(_PINNED_RATE),
        pinned_fraction=pinned / df.height,
        mean_annualized=mean_rate * _INTERVALS_PER_DAY * _ANNUALIZATION_DAYS,
        longest_negative_streak=longest_negative_streak(df),
    )


def plot_funding(df: pl.DataFrame, stats: FundingStats, out_png: Path) -> None:
    """Three panels: rate series (longest negative streak shaded), rolling
    30-day annualized, rolling 30-day pinned fraction."""
    import matplotlib  # noqa: PLC0415 - backend must be set before pyplot loads

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    ts = df.get_column("ts").to_list()
    rates_pct = [r * 100 for r in df.get_column("rate").to_list()]
    annualized = rolling_annualized(df)
    pinned_flag = df.with_columns(
        pl.col("rate_str")
        .map_elements(lambda s: float(Decimal(s) == _PINNED_RATE), return_dtype=pl.Float64)
        .alias("pinned")
    )
    pinned_rolling = (
        pinned_flag.sort("ts")
        .rolling(index_column="ts", period=f"{_ROLLING_DAYS}d")
        .agg(pl.col("pinned").mean().alias("fraction"))
    )

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(ts, rates_pct, linewidth=0.4, color="#1f77b4")
    axes[0].axhline(0.01, color="#888888", linestyle="--", linewidth=0.8, label="pinned +0.01%")
    axes[0].axhline(0.0, color="#000000", linewidth=0.6)
    streak = stats.longest_negative_streak
    if streak is not None:
        axes[0].axvspan(
            datetime.fromisoformat(streak.start),
            datetime.fromisoformat(streak.end),
            color="#d62728",
            alpha=0.2,
            label=f"longest negative streak ({streak.intervals} intervals)",
        )
    axes[0].set_ylabel("funding / 8h (%)")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].set_title(
        f"{stats.symbol} funding since {stats.first_interval[:10]} — "
        f"{stats.pinned_fraction:.1%} of intervals pinned at +0.01%"
    )

    axes[1].plot(
        annualized.get_column("ts").to_list(),
        [a * 100 for a in annualized.get_column("annualized").to_list()],
        linewidth=0.8,
        color="#2ca02c",
    )
    axes[1].axhline(0.0, color="#000000", linewidth=0.6)
    axes[1].set_ylabel(f"rolling {_ROLLING_DAYS}d annualized (%)")

    axes[2].plot(
        pinned_rolling.get_column("ts").to_list(),
        pinned_rolling.get_column("fraction").to_list(),
        linewidth=0.8,
        color="#9467bd",
    )
    axes[2].set_ylabel(f"rolling {_ROLLING_DAYS}d pinned fraction")
    axes[2].set_ylim(-0.05, 1.05)
    axes[2].set_xlabel("UTC")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def run(  # noqa: PLR0913 - script entry point wiring config to outputs
    base_url: str,
    symbol: str,
    start: datetime,
    out_dir: Path,
    raw_parquet: Path,
    client: httpx.Client | None = None,
) -> FundingStats:
    """Fetch, persist raw parquet, compute stats, write JSON + plot."""
    own_client = client is None
    c = client or httpx.Client(timeout=30.0)
    try:
        df = fetch_funding_history(base_url, symbol, start, c)
    finally:
        if own_client:
            c.close()
    raw_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(raw_parquet)
    stats = compute_stats(df, symbol)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "funding_stats.json").write_text(
        json.dumps(asdict(stats), indent=2) + "\n", encoding="utf-8"
    )
    plot_funding(df, stats, out_dir / "funding_analysis.png")
    return stats
