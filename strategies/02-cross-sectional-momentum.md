# Strategy 2 — Cross-Sectional / Relative-Strength Momentum

> **The best-documented equity edge** — Fama's "premier market anomaly," positive across ~200
> years and most countries, with the highest raw in-sample Sharpe of the classic factors. But
> read the fine print: the eye-popping numbers are a *leveraged long-short* figure you can't
> capture, the version you *can* own adds only a small tilt, and it carries a genuinely
> dangerous **negative-skew crash risk**.

**One-line honest anchor:** The investable long-only version delivers **roughly equity-like
returns with a small, regime-dependent tilt** (MTUM beat SPY by ~1%/yr since 2013, recently
near zero) — *not* a money machine, and *not* guaranteed to beat a plain index fund. Treat it
as a disciplined **tilt**, sized as a sleeve, never leveraged.

---

## 1. What it is (the mental model)

Cross-sectional momentum (a.k.a. *relative-strength* momentum) is a **ranking** strategy, not
a prediction strategy. You take a defined universe (stocks, sector ETFs, country ETFs, or
asset classes), measure how each performed over a trailing **3–12 months while skipping the
most recent month**, rank them best-to-worst **against each other**, then hold the top-ranked
**winners** and avoid or underweight the bottom-ranked **losers**. Between rebalances you do
nothing; every 1–6 months you re-rank and rotate into the new leaders.

The mental model: **"keep buying what's already working, relative to the pack."** The word
*cross-sectional* is the key distinction — you compare assets against their *peers* at a
single moment ("is XLK stronger than XLE right now?"). That's different from *time-series*
(trend) momentum, which compares each asset against its *own* past ([Strategy 1](01-trend-following.md)).
Cross-sectional is always fully invested in the best *relative* names; time-series can go
entirely to cash if everything is falling. **Serious practitioners run both:** rank
cross-sectionally to *pick* winners, then bolt on a time-series/absolute filter so you don't
hold "the best house in a burning neighborhood."

## 2. Why it works (the edge)

Primarily behavioral, with a risk-based tail attached:

1. **Under-reaction / slow information diffusion** — investors anchor on old prices and are
   slow to price news, so a stock that jumps on a genuine improvement tends to keep drifting up
   for months as the crowd catches on.
2. **The disposition effect** — people sell winners too early and hold losers too long,
   creating a temporary drag that resolves in the winner's favor and extends the trend.
3. **Herding / delegated flows** — performance-chasing by funds, index inclusion, and
   trend-followers push winners further (over-reaction), which eventually sets up the reversal.

**The risk-based leg matters for honesty:** part of what you earn is *compensation for bearing
momentum-crash risk.* Momentum is implicitly short a rare, violent factor — when a bear market
bottoms and beaten-down losers rip off the floor, a winners-minus-losers book can lose
spectacularly. Some of the premium is not free alpha; it's a wage for holding a strategy that
occasionally detonates. Fama-French (2008) still called momentum "the premier market anomaly"
— but the durable, capturable part for a long-only retail investor is **modest and shrinking**:
published anomaly returns run ~26% lower out-of-sample and ~58% lower *after* publication. The
edge is real, structural, **and** decaying — respect all three facts.

## 3. The honest return & risk reality

Be honest about **which reality** you get:

- The idealized **~1%/month, Sharpe ~0.7** premium is a **leveraged long-short** figure that
  lives disproportionately in the hard-to-short *loser* leg and in small, illiquid,
  expensive-to-borrow names. It is **largely NOT retail-capturable** and is eaten by trading
  and shorting costs.
- What you can actually own is the **long-only winners tilt.** Its real numbers: **MTUM**
  (iShares MSCI USA Momentum) beat SPY by only about **1%/yr since 2013** (~13.3% vs ~12.3%),
  and that edge is end-date-sensitive and has **narrowed to essentially zero** in recent years.
- **The correct framing is "roughly equity-like returns with a small, regime-dependent tilt"**
  — not a promise to beat an index fund.

**The risks are specific and real:**
- **Negative skew / "momentum crashes"** — the signature failure mode. After a sharp market
  bottom, the losers you avoided rebound violently while your defensive winners lag; the pure
  long-short factor **lost over 70% in a matter of months in 2009.** *(Do not let anyone tell
  you momentum has "symmetric" or "positive" skew — it is crash-prone negative skew.)*
- **Multi-year droughts** — MTUM lagged the S&P by roughly 3%/yr from 2021 to mid-2023
  (2021: +13% vs +26%; 2023: +9% vs +22%).
- **A real ~-34% drawdown** happened (MTUM, March 2020 — the *true ETF* figure, not a scarier
  simulated-index number).
- **High turnover** (150–200%/yr) with its cost and short-term-tax drag.
- **Alpha decay from crowding** — don't extrapolate the fattest historical backtest.

## 4. Core concepts you must understand

- **Cross-sectional vs. time-series momentum** — cross-sectional ranks assets against each
  other (always fully invested in the relative leaders); time-series compares each asset to its
  own history (can move to cash). *Complements:* use cross-sectional to **choose**, time-series
  to decide whether to be **in** the market at all.
- **Formation / lookback ("ranking") period** — the trailing window, classically 12 months,
  often 6. Shorter = more responsive but noisier/higher-turnover; longer = more stable. MSCI's
  index blends **both** a 6- and 12-month risk-adjusted return.
- **The "skip month" (the "12-1" convention)** — rank on returns from 12 months ago up to *one*
  month ago, excluding the most recent ~21 trading days. This avoids short-term reversal and
  bid-ask noise that would otherwise make you buy names about to bounce back down. **The single
  most important implementation detail** (Jegadeesh-Titman 1993).
- **Risk-adjusted momentum** — divide trailing return by the asset's volatility so the ranking
  isn't dominated by the single wildest name (MSCI uses excess return ÷ 3-year annualized vol).
- **Long-only vs. long-short (UMD / WML, "Winners-Minus-Losers")** — the pure academic factor
  is long winners *and* short losers; the bulk of the reported premium/Sharpe lives in the
  **short loser leg** (small, illiquid, hard-to-borrow), mostly uncapturable after real
  shorting costs. Retail realistically gets the **long-only winners tilt only.**
- **Turnover & alpha decay** — momentum is high-turnover by construction; costs and short-term
  taxes eat into it, and crowding shrinks future returns.
- **Momentum crash** — the signature negative-skew failure: after a sharp bottom, the losers
  you avoided/shorted rebound violently while your defensive winners lag, producing large fast
  drawdowns (2009 is the textbook case). Crashes cluster in high-vol, post-panic transitions.
- **Volatility scaling / risk-managed momentum** — because crashes cluster when factor
  volatility is high, scaling exposure *down* when recent realized vol is high roughly *doubled*
  the Sharpe in-sample (Barroso-Santa-Clara 2015: ~0.97 vs ~0.53). **Caveat:** that headline is
  in-sample, leveraged, and long-short — a long-only ETF buyer does *not* fully capture it, but
  the *idea* (cut size when vol spikes) is still usable as a drawdown-reducer.
- **Absolute / trend overlay** — a gate (only hold a ranked winner if it's also above its
  200-day MA, or its own 12-1 return is positive; otherwise hold cash/T-bills). This is what
  converts a purely *relative* strategy into one that can sidestep broad bear markets.

## 5. The rules

### Entry
- **Define a fixed universe in advance and write it down.** Starter universes: the **11 S&P
  sector SPDRs** (XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC); a set of 8–15
  asset-class ETFs; or S&P 500 constituents for single-stock. Keep it liquid.
- **Pick ONE ranking metric and freeze it.** Default: **12-1 total return** (cumulative return
  from 12 months ago to 1 month ago — *skip the most recent month*). More stable: the *average*
  of the 6-1 and 12-1 returns. Upgrade: risk-adjust by dividing each trailing return by that
  asset's volatility.
- **On each rebalance date, compute the metric for every asset and sort descending.** Rank 1 =
  strongest relative performer.
- **Decide breadth in advance:** hold the **top N** (e.g., top 3 of 11 sectors, or top 20% of a
  stock universe), equal-weighted. Don't eyeball it or override the rank.
- **Apply an absolute/trend filter before buying (strongly recommended):** only take a
  top-ranked name if it *also* passes a trend gate — price above its 200-day MA, or its own 12-1
  return positive. Any slot that fails the gate is parked in cash / T-bills (BIL/SGOV). **This
  is what keeps you out of a 2008-style decline.**
- **Enter on a scheduled date, not on a feeling** (month-end or a fixed trading day).
- **Log every entry:** date, asset, rank, score, price, size, target vs. actual exposure.

### Exit
- **Exit is rank-driven and scheduled, not P&L-driven.** On each rebalance date, re-rank the
  universe and **sell any holding that dropped out of your top-N.** You're not selling because
  a name "went up enough" — only because something else is now relatively stronger.
- **Use a rebalance buffer / hysteresis band** to cut needless turnover: e.g., only sell a
  holding when it falls below rank N+2 (not the instant it slips from 3 to 4). Index providers
  cap one-way turnover at ~30% per reconstitution.
- **Absolute-filter exit:** if a held name breaks its trend gate (below 200-day MA, or 12-1
  turns negative), exit to cash even if still nominally top-ranked — your circuit breaker for a
  name rolling over faster than the monthly clock.
- **Honor your fixed cadence** (1 / 3 / up to 6 months). Don't rebalance early because you're
  nervous or late because you're hopeful.
- **There is NO conventional profit target and NO fixed per-trade stop-loss** — a tight stop
  would chop you out of the very persistence you're harvesting. Your "stop" is the *combination*
  of (a) rotation on re-rank, (b) the absolute trend filter, and (c) portfolio-level volatility
  scaling.
- **Tax-awareness:** momentum generates short-term gains. In a taxable account, favor quarterly
  (or longer) cadence, use ETF wrappers or tax-advantaged accounts. Don't let taxes override a
  genuine signal, but *do* let them inform your cadence.

## 6. Risk management & position sizing

Because the return edge is small and the tail is fat, build defense in **four layers**:

1. **Volatility targeting (the single most valuable technique).** Momentum crashes cluster when
   recent factor volatility is high, so scale gross exposure *inversely* to recent realized vol.
   Set a target (retail-reasonable **10–12%**). `Exposure scalar = target_vol / realized_vol`,
   capped (e.g., 0.3–1.0 for an unleveraged account). If realized vol is 24% and target is 12%,
   you hold only 50% invested, 50% cash.
2. **Absolute/trend overlay** (crash-market defense) — the 200-day-MA / positive-own-momentum
   gate forces you to cash when the whole universe is falling.
3. **Sizing & diversification** — cap any single position; hold enough names that no single
   reversal is fatal; keep the *whole strategy* to a **sleeve** (10–30% of wealth).
4. **Drawdown & behavioral rules, pre-committed in writing** — expect multi-year droughts, a
   30%+ drawdown, and sudden violent reversals. Never override to "wait for a bounce"; never
   widen the universe or shorten the lookback mid-drawdown to chase.

**Position sizing — two steps:** (A) size each name for equal risk, then (B) scale the whole
book to a volatility target.
- **Step A:** equal-weight (honest default; top-3 → 33.3% each) *or* inverse-volatility weight
  `w_i = (1/vol_i) / Σ(1/vol_j)`.
- **Step B:** `Invested = s × Equity` where `s = target_vol / realized_vol` (capped 0.3–1.0);
  the rest sits in T-bills.

**Worked sizing example:** Equity $30,000, target 12% vol, recent realized book vol 18% →
`s = 12/18 = 0.67` → invest **$20,000**, hold **$10,000** in SGOV. Top-3 equal-weight → **$6,667
each.** If a panic pushes realized vol to 30%, `s = 0.40` → only $12,000 invested — the model
automatically shrinks you *into* the danger zone.

**Never lever a long-only momentum book to chase the academic numbers** — leverage multiplies
the crash proportionally and is the classic route to ruin. Use fractional Kelly at most; the
vol-target above is a cleaner, more robust governor.

## 7. A worked example

**Setup:** $30,000 account, universe = 11 S&P sector SPDRs, monthly rebalance, hold top 3
equal-weight, 12-1 ranking, absolute filter (positive 12-1 **and** above 200-day MA), 12% vol
target.

**Rebalance 1 (end of May).** Compute each sector's 12-1 return (end-of-May last year to
end-of-April this year — skipping May). Ranked:
`XLK +34% · XLC +28% · XLF +19% · XLI +14% · XLY +11% · XLV +6% · XLB +3% · XLP +1% · XLRE -2% · XLU -4% · XLE -12%`

Top 3 = **XLK, XLC, XLF**. All three are positive and above their 200-day MAs → pass the
filter. Recent realized book vol = 15% → `s = 12/15 = 0.80` → invest $24,000, $6,000 in SGOV.
Equal-weight: **$8,000 each.** Note you deliberately do **not** own XLE (worst performer) even
though "energy looks cheap" — that discipline *is* the strategy.

**Rebalance 2 (end of June).** June wobbled: XLE surged +11% on an oil spike; tech pulled back.
New ranks:
`XLK +26% · XLF +21% · XLI +17% · XLE +9% · XLC +8% ...`
Top 3 = **XLK, XLF, XLI**. Under a plain top-3 rule you sell XLC and buy XLI. **The whipsaw
lesson:** XLE just ripped +11% and you missed it — the normal cost of momentum. You do **not**
chase XLE now at rank 4; you only buy it if/when it enters your top 3. Realized vol rose to 20%
→ `s = 0.60` → invest $18,000 (the model de-risked you into turbulence).

**The crash scenario (why the overlay matters).** Suppose end-of-June is a market bottom after
a panic. Over July the beaten-down losers (XLE, small-caps) rocket +25% off the floor while your
defensive winners rise only +4%. A long-short book would be *crushed* here — this is the
2009-style momentum crash. Two things save the long-only version: (1) the absolute filter had
already moved much of the book to cash as vol spiked (`s` fell toward 0.4), capping the damage;
(2) by the next rebalance the ranks flip and you rotate into the new leaders. You still take a
real **20–35% drawdown** at the worst — but you avoid the leveraged blow-up. **Over a full
cycle the honest expectation is roughly equity-like returns with a small tilt, punctuated by
ugly stretches — not a smooth line.**

## 8. Common mistakes

- **Forgetting the skip month** — including the most recent month lets short-term reversal work
  against you.
- **Expecting the academic long-short numbers** — that ~1%/month, Sharpe ~0.7 is leveraged,
  short-heavy, and uncapturable. Realistic = *roughly equity-like with a small, recently
  near-zero tilt.*
- **Over-trading / ignoring costs and taxes** — lengthen cadence to quarterly, use rank
  buffers, prefer tax-advantaged accounts.
- **No absolute/trend overlay** — pure relative ranking stays fully invested into bear markets
  ("best house in a burning neighborhood").
- **No volatility management** — leaves you maximally exposed exactly when the strategy detonates
  (the >70% factor loss of 2009).
- **Abandoning the rules during a drought or reversal** — most people quit right before the
  recovery.
- **Overfitting parameters** — momentum is robust across 6–12mo lookbacks and 1–6mo holds; pick
  sensible standards and stop optimizing.
- **Ignoring alpha decay / crowding** — don't extrapolate the fattest backtest.
- **Discretionary overrides** and **leverage** — both forfeit the edge and magnify the crash.

## 9. How to learn it (the practice path)

1. **Backtest to internalize the shape (1–2 weeks).** Build the simplest version in a
   spreadsheet or Portfolio Visualizer: 11 sector SPDRs, top-3, monthly, 12-1 skip-month, +
   200-day-MA filter. Run it over **2005–today** so it *includes* 2008, the 2009 momentum crash,
   and the 2021–2023 lag. Goal: *see* the droughts and the 30%+ drawdown so they don't surprise
   you live. Add realistic costs (0.1–0.2%/rebalance).
2. **Paper trade the live process (2–3 months min).** Each month, on a fixed date, compute the
   ranks, apply filter + vol-target, and record the trades you *would* make — *before* seeing
   what happens. Journal how you **feel** ("hate buying XLK this high," "want to grab XLE").
3. **Trade small and scale in (3–6+ months).** Start with a 5–10% sleeve. Execute mechanically
   through at least one rebalance where you must sell a name you like and hold through a down
   month. Scale up only after the journal proves you can follow the process through a losing
   stretch.

**Ongoing discipline:** pre-write the full ruleset as a one-page trading plan; treat changes as
a deliberate, dated decision, never an in-the-moment reaction. Compare honestly to a plain index
fund — if after a few years you can't beat buy-and-hold net of costs and taxes, that's a valid,
honest outcome to accept (many can't; that's exactly what the evidence predicts).

## 10. Vehicles & tools

- **Data:** total-return price history with ≥13 months look-back (Yahoo/Stooq free, Norgate,
  Tiingo, or broker). Total return matters for high-dividend sectors (XLU/XLP).
- **Ranking engine:** a spreadsheet is enough for sector rotation; Python/pandas or R for stock
  universes.
- **Backtesting:** Portfolio Visualizer (beginner-friendly "Dual Momentum"/timing tools),
  QuantConnect, Zipline/backtrader. Always include costs and the skip month.
- **Off-the-shelf to study/use:** **MTUM** (iShares MSCI USA Momentum — read its methodology PDF
  as a rigorous template), **SPMO**, **PDP**, and global/international momentum ETFs.
- **Cash parking:** SGOV, BIL, or a money-market fund for slots that fail the trend gate or get
  de-risked.
- **Execution:** a broker with cheap ETF trades and **fractional shares** (helps equal-weighting)
  + a trade journal and a recurring rebalance-date reminder.

---

**Next:** [Strategy 3 — Volatility Risk Premium →](03-volatility-risk-premium.md)
Also essential: [Risk, Psychology, Taxes & Combining the Three →](04-risk-psychology-and-portfolio.md)

<sub>Educational material only; not investment advice. Figures are approximate and drawn from
published research; verify independently.</sub>
