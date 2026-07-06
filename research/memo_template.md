# Strategy decision memo — <STRATEGY NAME> (<date>)

> Template per BUILD_PLAN §3. One memo per strategy, produced in slice 4.4.
> Acceptance is an OWNER decision recorded at the bottom — never automatic.

## 1. Mechanism claim

State WHY this should make money, in one paragraph, before showing any number.
What inefficiency/behavior is harvested, who is on the other side, and why does
it persist? (Example scaffolding — S1: slow diffusion of information into
trends plus first-passage asymmetry; S2: liquidity provision into short-term
overreaction, governed to avoid crash regimes.)

## 2. Configuration under review

- Strategy / variant:
- Parameters (and how they were chosen — plateau evidence, not single cells):
- Data span, symbols, bar timeframe:
- Data provenance: IBKR curated / vendor / PROVISIONAL (Stooq daily) — label every era.
- Experiment-log trial count at memo time (TRUE N for deflated Sharpe):

## 3. Validation battery results

| Check | Result | Artifact |
|---|---|---|
| Baseline backtest (net of costs) | | metrics.json |
| Walk-forward (train/test, param stability) | | wf.json |
| Parameter heatmap + plateau assessment | | heatmap.png |
| Deflated Sharpe (TRUE trial count N=) | | |
| MC trade-order reshuffle (10k paths) drawdown p95 / worst | | mc.json |
| Slippage stress x1 / x2 / x3 | | stress.json |
| Era splits (label PROVISIONAL eras) | | eras.json |
| S2 only: same-close vs next-open fill — WORSE governs | | |

## 4. Tail metrics (gating — a change may not degrade these, §3)

- ES95 (mean of worst 5% trades):
- Worst trade / worst day:
- Max losing cluster:
- MC reshuffle p95 drawdown vs risk.yaml kill threshold headroom:

## 5. Costs & capacity

- Cost per round trip vs the ~$4.10 MES hurdle; share of gross P&L eaten by costs:
- Behavior at x2 / x3 slippage (does the edge survive stress?):

## 6. Known weaknesses & failure modes

Be specific: regimes where it loses, assumptions that can break, data caveats.

## 7. Verdict (OWNER ONLY)

- [ ] DEPLOY (paper) — conditions/limits:
- [ ] PARK — reason and what evidence would reopen it:

Signature/date:
