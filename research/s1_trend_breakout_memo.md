# Strategy decision memo — S1 TREND_BREAKOUT (DRAFT — DATA PENDING)

> Status: DRAFT. The implementation (slice 4.4) is complete and unit-tested;
> every results section below is BLOCKED on curated market data (§6 owner
> items: IBKR paper login + market-data subscription → slice 4.1 pipeline →
> `scripts/run_validation_battery.py`). No numbers in this memo may be filled
> from anything except that battery's artifacts.

## 1. Mechanism claim

Prices absorb information gradually: large allocation shifts and slow-moving
mandates (rebalancing, risk targeting, trend followers themselves) spread
order flow over days-to-weeks, so a close beyond an N-bar extreme is evidence
of imbalance that tends to continue rather than complete. The edge is paid
for by the first-passage asymmetry of the exit structure: a k*ATR trailing
stop converts continuation into a small number of large wins while capping
each failure at a known, sized loss (hit rate ~ a/(a+b), payoff ~ b/a — the
KA-1 signature the engine already reproduces on synthetic walks). The short
side fights equity index drift; whether it earns its seat is a TRACKED
EXPERIMENT (short-side on/off comparison), not an assumption.

## 2. Configuration under review

- Variant: TF-H (hourly, MES + M2K, deployment candidate); TF-D (daily, M2K)
  for research comparison only.
- Defaults: N=55, k=3, ATR period m=20; entries 13:30–21:00 UTC; stops 24h.
- Parameter changes only via the plateau rule on the N x k grid
  ({20,40,55,80,120} x {2.5,3,4}).
- Data: PENDING — 2y IBKR hourly+daily continuous (Panama), QC-clean.
- Experiment-log trial count at memo time: PENDING.

## 3. Validation battery results — ALL PENDING DATA

| Check | Result | Artifact |
|---|---|---|
| Baseline backtest (net of costs) | PENDING | research/s1_trend_breakout/metrics.json |
| Walk-forward | PENDING | wf.json |
| Heatmap + plateau assessment | PENDING | heatmap.png, plateau.json |
| Deflated Sharpe (TRUE N) | PENDING | deflated_sharpe.json |
| MC reshuffle (10k) | PENDING | mc.json |
| Slippage stress x1/x2/x3 | PENDING | stress.json |
| Era splits (label PROVISIONAL) | PENDING | eras.json |
| KA-4 2022 walkthrough | PENDING (test skips until data exists) | tests/known_answer/test_ka4_2022_walkthrough.py |
| Short-side on/off experiment | PENDING | |

## 4. Tail metrics (gating) — PENDING DATA

## 5. Costs & capacity — PENDING DATA

Round-trip hurdle to beat: ~$4.10 on MES (~3.3 ticks).

## 6. Known weaknesses & failure modes (design-phase, to be tested)

- Chop/range regimes: repeated false breakouts bleed k*ATR losses.
- Short side vs index drift (tracked experiment).
- Hourly session-boundary artifacts (maintenance-halt bars, holiday sessions).
- Parameter sensitivity if the N x k plateau turns out narrow.

## 7. Verdict (OWNER ONLY)

- [ ] DEPLOY (paper) — conditions/limits:
- [ ] PARK — reason:

Signature/date:
