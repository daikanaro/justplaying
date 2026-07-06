"""Binance funding tests — hermetic (mocked transport, synthetic frames)."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import polars as pl
import pytest

from qt.data.binance_funding import (
    FundingError,
    GeoBlockedError,
    compute_stats,
    fetch_funding_history,
    longest_negative_streak,
    plot_funding,
    rolling_annualized,
)

BASE = "https://fapi.example.test"
START = datetime(2020, 1, 1, tzinfo=UTC)


def funding_frame(rates: list[str], start: datetime = START) -> pl.DataFrame:
    ts = [start + timedelta(hours=8 * i) for i in range(len(rates))]
    return pl.DataFrame(
        {"ts": ts, "rate": [float(r) for r in rates], "rate_str": rates}
    ).with_columns(pl.col("ts").dt.replace_time_zone("UTC"))


def test_compute_stats_pinned_and_streak() -> None:
    df = funding_frame(
        ["0.00010000", "0.0001", "-0.00050000", "-0.00030000", "0.00020000", "0.00010000"]
    )
    stats = compute_stats(df, "BTCUSDT")
    assert stats.n_intervals == 6
    # Exact-decimal comparison: both "0.00010000" and "0.0001" are pinned.
    assert stats.pinned_fraction == pytest.approx(3 / 6)
    streak = stats.longest_negative_streak
    assert streak is not None
    assert streak.intervals == 2
    assert streak.start == (START + timedelta(hours=16)).isoformat()
    assert streak.end == (START + timedelta(hours=24)).isoformat()
    mean_rate = (0.0001 * 3 + 0.0002 - 0.0005 - 0.0003) / 6
    assert stats.mean_annualized == pytest.approx(mean_rate * 3 * 365)


def test_no_negative_streak_is_none() -> None:
    assert longest_negative_streak(funding_frame(["0.0001", "0.0002"])) is None


def test_rolling_annualized_constant_rate() -> None:
    # 60 days of constant +0.01%/8h: late windows hold 90 intervals ->
    # annualized = 90 * 0.0001 * (365/30) = 0.1095.
    df = funding_frame(["0.00010000"] * (60 * 3))
    ann = rolling_annualized(df, days=30)
    assert ann.get_column("annualized").tail(1)[0] == pytest.approx(0.1095)


def test_fetch_paginates_until_short_page() -> None:
    page_limit = 1000
    total = page_limit + 5
    all_rows: list[dict[str, int | str]] = [
        {
            "symbol": "BTCUSDT",
            "fundingTime": int((START + timedelta(hours=8 * i)).timestamp() * 1000),
            "fundingRate": "0.00010000",
        }
        for i in range(total)
    ]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        assert params["symbol"] == "BTCUSDT"
        start_ms = int(params["startTime"])
        calls.append(start_ms)
        batch = [r for r in all_rows if int(r["fundingTime"]) >= start_ms][:page_limit]
        return httpx.Response(200, json=batch)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        df = fetch_funding_history(BASE, "BTCUSDT", START, client)
    assert df.height == total
    assert len(calls) == 2
    assert calls[1] == int(all_rows[page_limit - 1]["fundingTime"]) + 1
    assert df.get_column("ts").is_sorted()


def test_geo_block_recorded() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(451, text="unavailable"))
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(GeoBlockedError, match="geo-blocked"),
    ):
        fetch_funding_history(BASE, "BTCUSDT", START, client)


def test_empty_history_rejected() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(FundingError, match="no funding"),
    ):
        fetch_funding_history(BASE, "BTCUSDT", START, client)


def test_naive_start_rejected() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    with (
        httpx.Client(transport=transport) as c,
        pytest.raises(FundingError, match="timezone-aware"),
    ):
        fetch_funding_history(BASE, "BTCUSDT", datetime(2020, 1, 1), c)


def test_plot_writes_png(tmp_path: Path) -> None:
    df = funding_frame(["0.00010000", "-0.00020000", "0.00030000"] * 30)
    stats = compute_stats(df, "BTCUSDT")
    out = tmp_path / "funding.png"
    plot_funding(df, stats, out)
    assert out.is_file()
    assert out.stat().st_size > 0
    # Stats survive JSON round-trip (the script persists them as JSON).
    parsed = json.loads(json.dumps(asdict(stats)))
    assert parsed["symbol"] == "BTCUSDT"
