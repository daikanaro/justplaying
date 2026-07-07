# QuantTrader

Systematic futures trading (MES/M2K micros), IBKR paper first. The authoritative build
spec is [BUILD_PLAN.md](BUILD_PLAN.md); session rules for Claude Code are in
[CLAUDE.md](CLAUDE.md); the live-arming checklist is [GO_NOGO.md](GO_NOGO.md).

## Setup

```sh
uv sync
uv run pytest && uv run mypy && uv run ruff check .
```

## Architecture (src/qt/)

- `config/` — pydantic schemas + fail-fast loader for the four config files in
  `config/`: `risk.yaml` (human-edited only), `instruments.yaml`, `strategies.yaml`,
  `data.yaml`. Unknown keys, duplicate YAML keys, and inf/nan values are startup failures.
- `data/` — IBKR pacing-aware downloader, roll table (5-day volume rule), Panama
  difference stitcher, QC (criticals block promotion to curated/), CME session calendar,
  VIX/events loaders, Binance funding (S3 deliverable).
- `costs/` — THE cost model (integer cents, session-aware slippage, stress multipliers).
  Single implementation imported by backtester and live executor; never forked.
- `backtest/` — event-driven engine: next-bar-open fills, gap-through stops, conservative
  limits, cent-exact FIFO accounting with the cash+marks==equity invariant checked on
  every event, stop widening structurally impossible.
- `strategies/` — S1 TREND_BREAKOUT and S2 MR_RSI2 per §3, §1 sizing (risk formula,
  vol-target overlay, contract caps).
- `validation/` — append-only experiment log (TRUE trial count), deflated Sharpe,
  walk-forward, heatmap + plateau rule, MC reshuffle, slippage stress, era splits.
- `oms/` — order state machine (hypothesis-tested), append-only fsync'd journal,
  idempotent submitter with bounded backoff, reconcile-or-HALT, native stop manager,
  thin ib_async adapter.
- `risk/` — pre-trade choke point, independent watchdog (§2 daily halt / kill),
  heartbeat dead-man switch, Telegram alerter, nightly journal-vs-statement recon.
- `campaign/` — §4.7 weekly tracking-error bands, the 4-consecutive-weeks clock,
  cost recalibration suggestions.

## Operational scripts (scripts/)

| Script | Purpose | Needs |
|---|---|---|
| `measure_rtt.py` | TCP RTT baseline → `data/baseline_rtt.json` | production box |
| `download_ibkr_history.py` | 2y MES/M2K contract history → `data/raw/` | IB Gateway |
| `build_continuous.py` | raw → roll table → Panama → QC → `data/curated/` | raw data |
| `fetch_vix.py` / `fetch_binance_funding.py` | auxiliary data + S3 stats | egress |
| `run_validation_battery.py` | full §3 battery + memo artifacts for S1/S2 | curated data |
| `chaos_drills.py a\|b\|c\|d` | §4.5 acceptance drills | IB Gateway |
| `watchdog.py` | independent risk watchdog process | IB Gateway |
| `nightly_recon.py` | journal vs Flex statement | statement CSV |
| `weekly_report.py` | §4.7 bands + campaign clock | campaign inputs |

## Known-answer suite (tests/known_answer/)

KA-1 (no edge on GBM + first-passage signature), KA-2 (hand-computed 10-bar fixture,
matched to the cent), KA-3 (MR governor grid on P = F + u), KA-4 (2022 MES walkthrough —
skips until curated data exists; a skip is not a pass).

## Owner items (§6) — the current blockers

IBKR paper login + market-data subscription (unblocks data → KA-4 → memos → drills →
campaign), Telegram token, vendor deep-history decision, monthly `events.csv`, tax
consultation before live. Live starts at $1–2K, never $20K.

## Ops

`docs/windows_ops.md` — Task Scheduler jobs, IB Gateway auto-restart, w32tm clock sync,
tzdata. Runtime money-path artifacts live in `data/journal/` (git-ignored); the `HALT`
flag file blocks the engine until the owner deletes it.
