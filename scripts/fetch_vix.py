"""Download VIX daily history (CBOE public CSV) into data/curated/vix/."""

from __future__ import annotations

import sys
from pathlib import Path

from qt.config import DataConfig, load_config
from qt.data.vix import VixError, fetch_vix, save_vix

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    data_cfg = load_config(REPO_ROOT / "config" / "data.yaml", DataConfig)
    try:
        df = fetch_vix(data_cfg.sources.vix.url)
    except VixError as exc:
        print(f"VIX fetch failed: {exc}", file=sys.stderr)
        return 1
    out = REPO_ROOT / Path(data_cfg.paths.curated_dir) / "vix" / "vix_daily.parquet"
    save_vix(df, out)
    last = df.tail(1)
    print(f"{df.height} rows -> {out}")
    print(f"latest: {last.get_column('date')[0]} close {last.get_column('close')[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
