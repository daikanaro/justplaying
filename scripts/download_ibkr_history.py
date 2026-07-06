"""Download ~2y of MES/M2K contract history from IBKR into data/raw/ibkr/.

Requires a running IB Gateway (paper, default port 4002) with the futures
market-data subscription active — OWNER items (§6). Pacing-aware and
resumable: finished contract files are skipped on re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from qt.config import DataConfig, RiskConfig, load_config
from qt.data.contracts import contracts_covering
from qt.data.ibkr_download import DownloadError, download

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    args = parser.parse_args()

    data_cfg = load_config(REPO_ROOT / "config" / "data.yaml", DataConfig)
    risk_cfg = load_config(REPO_ROOT / "config" / "risk.yaml", RiskConfig)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=365 * data_cfg.ibkr.history_years)
    raw_root = REPO_ROOT / Path(data_cfg.paths.raw_dir)

    contracts = [
        c
        for symbol in risk_cfg.instrument_whitelist
        for c in contracts_covering(symbol, start, today)
    ]
    print(f"{len(contracts)} contracts to cover {start}..{today}")
    try:
        written = asyncio.run(
            download(contracts, ["1 day", "1 hour"], raw_root, host=args.host, port=args.port)
        )
    except DownloadError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"wrote {len(written)} files under {raw_root / 'ibkr'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
