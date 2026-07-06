"""Fetch BTCUSDT funding history and produce the three S3 statistics + plot.

Reads config/data.yaml; writes raw parquet under data/raw/ and the stats JSON
+ plot under research/binance_funding/. Exits non-zero (with the fact recorded
on stderr) if the endpoint is geo-blocked from this machine.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from qt.config import DataConfig, load_config
from qt.data.binance_funding import FundingError, GeoBlockedError, run

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    data_cfg = load_config(REPO_ROOT / "config" / "data.yaml", DataConfig)
    funding = data_cfg.sources.binance_funding
    start = datetime.fromisoformat(funding.start).replace(tzinfo=UTC)
    out_dir = REPO_ROOT / "research" / "binance_funding"
    raw = REPO_ROOT / Path(data_cfg.paths.raw_dir) / "binance" / f"{funding.symbol}_funding.parquet"
    try:
        stats = run(funding.base_url, funding.symbol, start, out_dir, raw)
    except GeoBlockedError as exc:
        print(f"GEO-BLOCKED (recorded per §3 S3): {exc}", file=sys.stderr)
        return 2
    except FundingError as exc:
        print(f"funding download failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"{stats.symbol}: {stats.n_intervals} intervals "
        f"({stats.first_interval} .. {stats.last_interval})"
    )
    print(f"pinned at +0.01%: {stats.pinned_fraction:.2%}")
    print(f"mean annualized funding: {stats.mean_annualized:.2%}")
    if stats.longest_negative_streak:
        s = stats.longest_negative_streak
        print(f"longest negative streak: {s.intervals} intervals ({s.start} .. {s.end})")
    print(f"artifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
