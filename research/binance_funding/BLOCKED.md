# Binance funding fetch — blocked from the build environment (recorded fact)

- **When:** 2026-07-06T16:06Z
- **What:** `scripts/fetch_binance_funding.py` and `scripts/fetch_vix.py` both failed:
  the cloud session's egress proxy answered **403 to CONNECT** for
  `fapi.binance.com:443` and `cdn.cboe.com:443` (policy denial, verified via the
  proxy status endpoint). This is the sandbox's network allowlist — **not** a
  Binance geo-block of the kind §3 S3 anticipates, and it says nothing about
  reachability from the production machine in Kazakhstan.
- **What was verified anyway:** the module is fully unit-tested against a mocked
  transport (pagination, exact-decimal pinned detection, rolling annualization,
  negative-streak, geo-block handling, plot rendering) — 213-test suite green.

## Owner resolution options (per CLAUDE.md conflict protocol)

1. Allow `fapi.binance.com` and `cdn.cboe.com` in this Claude Code environment's
   network policy and re-run both scripts here, or
2. Run `uv run python scripts/fetch_binance_funding.py` and
   `uv run python scripts/fetch_vix.py` from your own machine.

Either path produces `research/binance_funding/funding_stats.json` +
`funding_analysis.png` (delete this file once they exist) and
`data/curated/vix/vix_daily.parquet`. If Binance answers HTTP 403/451 from
Kazakhstan, the script records THAT as the real geo-block per §3 S3.
