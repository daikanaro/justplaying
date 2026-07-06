"""Build Panama-adjusted continuous series from raw IBKR contract files.

Pipeline per whitelisted symbol: raw per-contract parquet -> roll table
(volume rule) -> Panama stitch (daily + hourly) -> QC -> promote to
data/curated/ only if the QC report has zero criticals. QC reports are
written next to the curated files either way.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from qt.config import DataConfig, RiskConfig, load_config
from qt.data.contracts import ContractMonth, contracts_covering
from qt.data.ibkr_download import raw_parquet_path
from qt.data.panama import stitch_panama
from qt.data.qc import PromotionBlockedError, QCReport, qc_daily, qc_hourly
from qt.data.roll_table import build_roll_table, roll_table_frame

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_contract_bars(
    raw_root: Path, contracts: list[ContractMonth], bar_size: str
) -> dict[str, pl.DataFrame]:
    out: dict[str, pl.DataFrame] = {}
    for contract in contracts:
        path = raw_parquet_path(raw_root, contract, bar_size)
        if path.is_file():
            out[contract.contract_id] = pl.read_parquet(path)
    return out


def build_symbol(
    symbol: str, raw_root: Path, curated_root: Path, data_cfg: DataConfig
) -> list[QCReport]:
    today = datetime.now(UTC).date()
    start = today - timedelta(days=365 * data_cfg.ibkr.history_years)
    contracts = contracts_covering(symbol, start, today)

    daily = load_contract_bars(raw_root, contracts, "1 day")
    hourly = load_contract_bars(raw_root, contracts, "1 hour")
    with_data = [c for c in contracts if c.contract_id in daily]
    if len(with_data) < 2:  # noqa: PLR2004 - stitching needs at least two contracts
        msg = (
            f"{symbol}: only {len(with_data)} contracts have raw daily data under "
            f"{raw_root / 'ibkr'} — run scripts/download_ibkr_history.py first "
            "(requires IB Gateway; OWNER item §6)"
        )
        raise FileNotFoundError(msg)

    volumes = {
        cid: df.select(pl.col("ts").dt.date().alias("date"), "volume").group_by("date").sum()
        for cid, df in daily.items()
    }
    rolls = build_roll_table(
        with_data,
        volumes,
        volume_lookback_days=data_cfg.roll.volume_lookback_days,
        fallback_days_before_expiry=data_cfg.roll.fallback_days_before_expiry,
    )

    reports: list[QCReport] = []
    out_dir = curated_root / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    roll_table_frame(rolls).write_parquet(out_dir / "roll_table.parquet")

    for label, bars, qc_fn in (
        ("daily", daily, qc_daily),
        ("hourly", hourly, qc_hourly),
    ):
        continuous, audit = stitch_panama(bars, rolls)
        report = qc_fn(continuous, f"{symbol} {label}", data_cfg.qc.outlier_sigma)
        reports.append(report)
        (out_dir / f"qc_{label}.txt").write_text(report.to_text() + "\n", encoding="utf-8")
        audit_frame = pl.DataFrame(
            {
                "date": [a.date for a in audit],
                "from_contract": [a.from_contract for a in audit],
                "to_contract": [a.to_contract for a in audit],
                "offset": [a.offset for a in audit],
            }
        )
        audit_frame.write_parquet(out_dir / f"roll_adjustments_{label}.parquet")
        if report.is_clean:
            continuous.write_parquet(out_dir / f"continuous_{label}.parquet")
        else:
            msg = f"{symbol} {label}: criticals present, not promoting\n{report.to_text()}"
            raise PromotionBlockedError(msg)
    return reports


def main() -> int:
    data_cfg = load_config(REPO_ROOT / "config" / "data.yaml", DataConfig)
    risk_cfg = load_config(REPO_ROOT / "config" / "risk.yaml", RiskConfig)
    raw_root = REPO_ROOT / Path(data_cfg.paths.raw_dir)
    curated_root = REPO_ROOT / Path(data_cfg.paths.curated_dir)
    failures = 0
    for symbol in risk_cfg.instrument_whitelist:
        try:
            reports = build_symbol(symbol, raw_root, curated_root, data_cfg)
        except (FileNotFoundError, PromotionBlockedError) as exc:
            print(str(exc), file=sys.stderr)
            failures += 1
            continue
        for report in reports:
            print(report.to_text())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
