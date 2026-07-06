# Strategy decision memo — S2 MR_RSI2 (DRAFT — DATA PENDING)

> Status: DRAFT. The implementation (slice 4.4) is complete and unit-tested;
> every results section below is BLOCKED on curated market data (§6 owner
> items). No numbers in this memo may be filled from anything except
> `scripts/run_validation_battery.py` artifacts. Both fill modes are
> mandatory and the WORSE governs (§3).

## 1. Mechanism claim

Short-horizon overreaction in equity indices: after a cluster of down days
(RSI(2) < 10) inside an uptrend (close > SMA200), liquidity demanders have
overpaid for immediacy and prices tend to snap back within days. S2 sells
that immediacy. The governors are the strategy: the trend filter keeps it out
of downtrends where "oversold" keeps getting more oversold; the hard
2.5*ATR(14) stop is a model-falsification line (crash regime, not
overreaction); the 5-bar time stop kills the trade when the snap-back thesis
has expired; the ATR/VIX/event gates refuse regimes where the tail dominates.
KA-3 already demonstrates on synthetic P = F + u worlds that these governors
are roughly mean-neutral while cutting ES95 ~5.6x and the worst trade ~14x.
NO scale-ins — deliberately removed as a tail multiplier.

## 2. Configuration under review

- Daily bars; long-only v1. M2K primary; MES only when the ATR gate passes.
- Entry: RSI(2) < 10 AND close > SMA(200) AND ATR gate AND VIX < 35 AND no
  calendar event next session.
- Exit: close > previous high OR RSI(2) > 65 OR 5-bar time stop (next-open);
  hard stop 2.5*ATR(14) below entry, resting, never widened.
- Era-split validation mandatory: <=2012 / 2013–2019 / 2020–present
  (pre-IBKR-window eras run on PROVISIONAL data until the vendor decision, §6).
- Experiment-log trial count at memo time: PENDING.

## 3. Validation battery results — ALL PENDING DATA

| Check | Result | Artifact |
|---|---|---|
| Baseline, next-open fills | PENDING | research/s2_mr_rsi2/next_open/metrics.json |
| Baseline, same-close fills (lookahead-adjacent) | PENDING | research/s2_mr_rsi2/same_close_LOOKAHEAD/metrics.json |
| Governing mode (WORSE of the two) | PENDING | fill_modes.json |
| Walk-forward | PENDING | wf.json |
| Deflated Sharpe (TRUE N) | PENDING | deflated_sharpe.json |
| MC reshuffle (10k) | PENDING | mc.json |
| Slippage stress x1/x2/x3 | PENDING | stress.json |
| Era splits (PROVISIONAL labeled) | PENDING | eras.json |

## 4. Tail metrics (gating) — PENDING DATA

§3: no change may degrade ES95, worst day, or max losing cluster, even if
Sharpe improves.

## 5. Costs & capacity — PENDING DATA

## 6. Known weaknesses & failure modes (design-phase, to be tested)

- Crash regimes faster than the hard stop (gap-through risk is modeled but
  still real money).
- VIX gate uses the prior close: a same-day vol spike is invisible until the
  next bar.
- Live implementation computes the signal ~5 min before the close; slippage
  vs the true close must be logged and reconciled against the same-close
  backtest mode (§3).

## 7. Verdict (OWNER ONLY)

- [ ] DEPLOY (paper) — conditions/limits:
- [ ] PARK — reason:

Signature/date:
