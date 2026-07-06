"""VIX daily closes from the CBOE public CSV (BUILD_PLAN §1 auxiliary data)."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import polars as pl


class VixError(Exception):
    """VIX download or validation failed."""


_EXPECTED_HEADER = {"DATE", "OPEN", "HIGH", "LOW", "CLOSE"}


def parse_vix_csv(text: str) -> pl.DataFrame:
    """Parse CBOE's VIX_History.csv into (date, open, high, low, close)."""
    try:
        df = pl.read_csv(io.StringIO(text))
    except Exception as exc:
        msg = f"VIX CSV unparseable: {exc}"
        raise VixError(msg) from exc
    if not _EXPECTED_HEADER.issubset({c.upper() for c in df.columns}):
        msg = f"VIX CSV header {df.columns} missing {sorted(_EXPECTED_HEADER)}"
        raise VixError(msg)
    df = df.rename({c: c.lower() for c in df.columns}).select(
        pl.col("date").str.to_date("%m/%d/%Y"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
    )
    return validate_vix(df)


def validate_vix(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        msg = "VIX frame is empty"
        raise VixError(msg)
    if df.get_column("date").is_duplicated().any():
        msg = "VIX frame has duplicate dates"
        raise VixError(msg)
    if not df.get_column("date").is_sorted():
        msg = "VIX frame dates are not ascending"
        raise VixError(msg)
    if (df.get_column("close") <= 0).any():
        msg = "VIX frame has non-positive closes"
        raise VixError(msg)
    return df


def fetch_vix(url: str, client: httpx.Client | None = None) -> pl.DataFrame:
    """Download and validate the full VIX daily history."""
    own_client = client is None
    c = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        response = c.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        msg = f"VIX download failed from {url}: {exc}"
        raise VixError(msg) from exc
    finally:
        if own_client:
            c.close()
    return parse_vix_csv(response.text)


def save_vix(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
