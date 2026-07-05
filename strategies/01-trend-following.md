# Strategy 1 — Trend Following / Time-Series Momentum (Managed Futures)

> **The #1 pick.** Deepest out-of-sample evidence of any anomaly, the one strategy you can
> capture in its *real* long/short form as an individual, **positive skew**, and documented
> "crisis alpha." Its catch: modest standalone returns and multi-year flat stretches that
> make people quit at exactly the wrong time.

**One-line honest anchor:** Expect *single-digit* standalone returns at a low **~0.3–0.5
live Sharpe**, with 20–25%+ drawdowns and a ~30–40% win rate where a few big winners carry
everything. Its value is **risk-adjusted diversification and crash-hedging**, not high
standalone returns.

---

## 1. What it is (the mental model)

Trend following is the systematic strategy of **buying markets that have been going up and
short-selling markets that have been going down**, across a broad, diversified basket of
futures — stock indices, government bonds, currencies, and commodities (energy, metals,
grains). You don't forecast where prices are headed; you let each market's own recent price
action tell you which side to be on, then ride the move for weeks to months until it
reverses.

**You are a surfer, not a weather forecaster.** You can't predict the ocean, but when a wave
forms you paddle with it and ride until it breaks. The technical name for the signal is
*time-series momentum* (TSMOM): you compare each market to **its own** past ("is gold higher
than it was 6–12 months ago?"), which is different from *cross-sectional* momentum (ranking
markets against each other — that's [Strategy 2](02-cross-sectional-momentum.md)).

The trade-level experience is deliberately uncomfortable: you win only ~30–40% of the time,
take many small losses (whipsaws), and a handful of enormous winners in strong trends pay for
everything. This produces a **positive-skew, insurance-like** return profile that tends to do
best precisely when stocks are crashing in slow motion (2008, 2022) — its famous **crisis
alpha.**

## 2. Why it works (the edge)

The edge is real but modest, and comes from three overlapping sources:

1. **Behavioral under-reaction.** Investors are slow to fully price news; information diffuses
   gradually, and herding plus the *disposition effect* (selling winners too early, holding
   losers too long) creates persistent, exploitable price drift.
2. **Structural risk transfer.** In futures markets, commercial hedgers (a farmer hedging
   wheat, an airline hedging jet fuel) systematically pay speculators to absorb price risk.
   Trend followers are among those paid speculators. Macro fundamentals and central-bank
   policy also change slowly and trend for months.
3. **Crisis dynamics / long volatility.** Prolonged crises unfold over months, and trend
   systems ride them short. That's why the strategy is *convex* and "long volatility" — it
   makes money when correlations spike and diversified portfolios break.

**Be honest about the limits:** this is a crowded, well-known edge that has partially decayed
since its 1980s–90s golden era. Idealized backtests look like a ~1.0 Sharpe machine; **live,
net-of-fee realized Sharpe is only ~0.3–0.5.** You are paid a modest premium to hold an
uncomfortable, patience-testing return stream that most people abandon at the worst time.

## 3. The honest return & risk reality

- **Live benchmark:** the **SG Trend Index** has returned roughly **4.9%/yr net since 2000**
  at a realized Sharpe of only **~0.3–0.5**, including a **2009–2018 "lost decade"** that was
  essentially flat. Budget your expectations from *this* number.
- **Keep two buckets separate.** The famous "positive return in every decade since the 1880s
  across ~67 markets at ~1.0 gross Sharpe" (Hurst–Ooi–Pedersen) is a well-constructed
  **simulation** (it applies simulated costs and fees) — but it is *hypothetical*. Live
  results run well below it. Use the simulation to understand the strategy's *character*; use
  4.9% / 0.3–0.5 to budget your *returns*.
- **Crisis alpha is the real prize** and is if anything understated: the SG Trend Index
  returned about **+20.9% in 2008** and **+27.3% in 2022** — years a 60/40 portfolio got
  hammered. This convex payoff during protracted crises is the core portfolio justification.
- **Portfolio value:** adding a ~20% trend sleeve to a 60/40 portfolio has historically lifted
  the Sharpe from roughly **0.38 → 0.53** and cut max drawdown — but this is *regime-dependent*
  (trend drags during calm bull markets).
- **Its natural enemy:** sharp **V-shaped reversals** (the March 2020 COVID snapback, the 2011
  whipsaws) produce clusters of small losses. Expect them; don't "fix" the system after one.
- **Costs roughly halve gross returns.** Retail managed-futures ETFs charge ~0.85–0.95% and
  have only ~5 years of live history with real tracking error vs. the true CTA composite.

## 4. Core concepts you must understand

- **Time-series vs. cross-sectional momentum** — TSMOM compares each market to its own history
  and can be long some markets and short others at once. Trend following = TSMOM.
- **Managed futures / CTA** — "CTA" (Commodity Trading Advisor) is the regulatory label for
  pros who run these programs; most are 60–90% trend following under the hood.
- **Convexity / positive skew / "long volatility"** — the return profile is like *owning*
  insurance: many small premiums paid out (losing trades), rare large payoffs (big trends).
- **Crisis alpha** — the tendency to profit during extended equity bear markets, because
  those are trends the system rides short. The strategy's single most valuable property.
- **Volatility targeting / risk parity** — positions are sized by *risk*, not dollars, so a
  sleepy bond and a manic natural-gas contract contribute equal risk; total portfolio vol is
  held near a constant (~10–15%/yr).
- **Signal families** — (a) moving-average crossover (50-day crossing 200-day, or price vs.
  200-day SMA); (b) breakout / Donchian channel (buy a new N-day high, exit/reverse on a new
  N-day low — the classic "Turtle" rules used 20- and 55-day breakouts). All just measure
  *which direction price has been going.*
- **Diversification across many markets** — you need 30–100+ markets across 4+ asset classes.
  The math only works with enough uncorrelated shots for the few big winners to appear; a
  5-market system is mostly noise.
- **Notional vs. margin (leverage)** — futures control large notional with small margin.
  Powerful and dangerous; the mechanism behind both the strategy's efficiency and DIY
  margin-call blowups. **If you can't state your true notional leverage, you're
  over-leveraged.**
- **Whipsaw** — a false breakout that reverses right after you enter. The normal cost of
  doing business.
- **Continuous / back-adjusted futures data & roll yield** — futures expire, so you "roll" to
  the next contract and stitch a continuous series for signals; the roll has a cost/benefit
  (contango vs. backwardation).

## 5. The rules

### Entry
- **Fix your universe first:** a diversified basket of liquid futures across 4+ sectors —
  equity indices (MES, MNQ), rates/bonds (ZN, ZB, ZF, Bund), FX (6E, 6J, 6B, 6A), commodities
  (MCL, MGC, SI, HG, ZC, ZW, ZS, NG). Aim for **20–50+ markets**; more is better.
- **Pick ONE signal rule and apply it identically to every market, long and short.**
  Beginner-friendly options:
  - **(A) Trend filter:** long when price closes above its 200-day SMA, short when below.
  - **(B) Dual moving-average crossover:** long when 50-day SMA > 200-day SMA, short/flat when
    below.
  - **(C) Donchian breakout:** buy a new 50-day (or 20-day) closing high, short a new 50-day
    (or 20-day) closing low.
- **Trade symmetrically** — no "I don't want to short bonds" overrides.
- **Enter only on a confirmed signal at a fixed cadence** (evaluate on the daily or weekly
  close). No intraday discretion, no anticipating the crossover.
- **Compute the size before you place the trade** (see §6). A signal without a computed size
  is not a tradeable entry.
- **Respect a per-sector / correlation cap** — bonds move together; treat correlated clusters
  as one and scale them down.
- **Pre-commit the whole rule set in writing.**

### Exit
- **Exit on signal reversal — the primary exit.** Entered long on price > 200-day SMA? Exit
  (and possibly reverse short) when price closes below it. The exit is symmetric with the
  entry.
- **Trail with a volatility-based stop** to protect open profit: a *chandelier* stop =
  highest-high-since-entry − 3×ATR. It ratchets up as the trend rises, never down.
- **DO NOT use fixed profit targets.** Letting winners run is the *entire* source of the edge;
  capping a winner at +2R destroys the fat right tail that pays for all the losers. **This is
  the single most important exit discipline.**
- **Cut losers fast and mechanically** at the initial stop (entry − 2–3×ATR = your −1R). No
  averaging down.
- **Re-evaluate only on your fixed cadence.** Don't hand-manage tick by tick.
- **Roll before expiry** if the signal is still active.

## 6. Risk management & position sizing (this *is* the strategy)

Entries are almost interchangeable; **survival and sizing** separate winners from blowups.

**Core risk rules**
1. **Per-trade risk:** risk a small fixed fraction of equity to the initial stop — **0.3–0.75%**
   (use **0.5%** as a default). With ~30–50 positions, no single market dominates.
2. **Portfolio volatility target:** hold total annualized portfolio vol near constant
   (~10–15%/yr). When markets get wild, *shrink* contract counts; when they calm, grow them.
3. **Sector/cluster caps** so one macro event can't sink the book.
4. **Portfolio heat cap:** limit total simultaneous open risk (sum of all −1R stops) to,
   e.g., 15–25% of equity.
5. **Leverage discipline:** keep a cash cushion so a bad week never forces liquidation.
6. **Drawdown expectations, pre-accepted in writing:** this strategy *will* hand you 20–25%+
   drawdowns and multi-year flat stretches. **Decide now that you will not change the system
   during a drawdown** — quitting at the bottom is the dominant failure mode.

**Position sizing — size by RISK, not dollars**

Primary method (easiest to run):
```
Contracts N = (Equity × Risk%) / (StopDistance × PointValue)
```
- `Risk%` = fraction risked to the initial stop (0.5% = 0.005)
- `StopDistance` = usually 2–3 × the 20-day ATR
- `PointValue` = dollar value of a 1-point move (Micro Gold MGC = $10 per $1/oz; ES = $50/pt;
  MES = $5/pt)

Round **down** to whole contracts. If the answer is < 1, the market is too big for your
account at that risk — use a **micro** contract or skip it. (This is exactly why retail books
are built from micro futures: MES, MNQ, MCL, MGC, M2K let a $50–250k account hold 30–50
positions at proper small risk.)

**Kelly caveat:** full-Kelly on a ~0.4-Sharpe, fat-tailed strategy implies ruinous leverage.
Use a *small fraction* of Kelly (¼ or less). When in doubt, size **smaller** — you cannot
compound if you blow up.

## 7. A worked example

**Account:** $250,000. **System:** 50/200-day SMA crossover, long/short, ~40 micro-futures
markets, 0.5% risk per trade, ~12%/yr portfolio vol target.

**Winning trend — Gold**
- Signal: 50-day SMA crosses above 200-day SMA. Gold = $2,000/oz. Micro Gold (MGC) = 10 oz, so
  a $1/oz move = $10 per contract.
- 20-day ATR = $30/oz. Initial stop = 3×ATR = $90 below entry, at $1,910. Risk per contract =
  $90 × 10 = **$900.**
- Size N = ($250,000 × 0.005) / $900 = $1,250 / $900 = 1.39 → **round down to 1 contract.**
  (Full-size GC, 100 oz, would risk $9,000/contract — 7× your budget — which is exactly why
  you use the micro.)
- The trend runs ~4 months to $2,360. A chandelier trailing stop (highest high − 3×ATR) has
  ratcheted to $2,300. Price pulls back and hits it. **Exit at $2,300.**
- Result: ($2,300 − $2,000) × 10 × 1 = **+$3,000 = +1.2% of the account, or +3.3R** (risked
  $900, made $3,000). You never used a profit target — *letting it run* turned a 1R risk into
  a 3.3R win.

**Losing whipsaw — Silver, same week**
- Breakout long, reverses two days later, initial stop hit. Loss = **−1R ≈ −0.5% of account.**
  Clean, small, mechanical. No averaging down.

**Why a 30–40% win rate still works (the portfolio picture)**
Across ~40 markets in a year you might get 24 losers averaging −0.4R and 16 winners. Most
winners are small (+0.5R to +1.5R), but **3–4 monster trends** (a bond bull run, an oil spike,
a currency devaluation) print **+5R to +15R each.** Those few fat right-tail winners carry the
*entire year* while two-thirds of your individual trades lost money. That asymmetry — many
tiny losses, rare huge wins — **is** the strategy. Any impulse to "improve" the win rate by
taking profits early quietly kills it.

## 8. Common mistakes

- **Quitting during a flat stretch or after a drawdown — THE dominant failure mode.** The
  strategy is engineered to test your patience; abandoning it at the bottom converts a
  temporary drawdown into a permanent loss.
- **Over-leveraging the futures account** into a margin-call forced liquidation — the classic
  DIY blowup.
- **Trading too few markets** — with 5–10 instruments you eat the whipsaws without enough
  shots for the rare big winners.
- **Adding profit targets / taking winners early** — decapitates the fat right tail; the
  fastest way to turn positive expectancy negative.
- **Curve-fitting parameters** (the "perfect" 47/213-day crossover). Simple round-number rules
  that work across many markets beat finely-tuned ones.
- **Discretionary overrides** — every skipped short or doubled "favorite" is a bet against
  your own edge.
- **Ignoring costs** — a backtest without realistic costs is fiction.
- **Confusing the simulation with live returns** — budget from ~4.9%/yr live, not "positive
  every decade."
- **Reacting to single-trade P&L instead of expectancy over hundreds of trades.**

## 9. How to learn it (the practice path)

1. **Backtest a dead-simple rule yourself.** Code the 200-day SMA (or 50/200 crossover)
   long/short on 20–50 back-adjusted futures with *realistic costs* and volatility-based
   sizing. Don't optimize — the goal is to *see* the long flat stretches and the handful of
   trades that make the year.
2. **Paper/sim trade the live system for 6–12 months.** Feel a string of whipsaws, feel a
   4-month flat stretch, and practice **not** overriding. This is where most learning happens.
3. **Keep a decision journal** — for every signal log the rule, size, outcome, and your
   *emotional pull* ("wanted to take profit early"). It's how you catch discretion creeping in.
4. **Start tiny and real** — either a small managed-futures ETF sleeve (DBMF/KMLM/CTA at
   ~5–15% of your portfolio) for zero operational risk, or 1–2 micro contracts at 0.25% risk.
5. **Scale in only after you've survived a real drawdown by the rules.**
6. **Benchmark honestly against the SG Trend Index**, not a backtest. Tracking the pro
   composite through good and bad regimes means your execution is sound — even when boring.

**Above all:** pre-commit every rule in writing and, ideally, **automate execution** so the
machine — not your mood — pulls the trigger.

## 10. Vehicles & tools

- **Signals:** SMAs (50/100/200-day), Donchian channels (20 & 55-day), price-vs-MA filters.
- **Risk/sizing:** ATR (20-day) for stops and sizing; rolling realized-vol for vol targeting.
- **Data:** back-adjusted **continuous** futures (Norgate, CSI, Nasdaq Data Link, or broker
  feed). Raw expiring contracts break your signals.
- **Brokers (DIY futures):** Interactive Brokers, Tradovate, NinjaTrader, AMP — pick deep
  micro-futures access (MES, MNQ, MCL, MGC, M2K, MYM).
- **Backtesting/automation:** Python (vectorbt, backtrader), TradingView Pine, or Excel for a
  single-market prototype.
- **Hands-off vehicles (no futures account):** managed-futures ETFs — **DBMF** (~0.85%),
  **KMLM** (0.90%), **CTA**, **RSST**; mutual funds AQMIX/ASFYX. ~5 years live history,
  real tracking error.
- **Reality-check benchmark:** the **SG Trend Index** / SG CTA Index.

---

**Next:** [Strategy 2 — Cross-Sectional Momentum →](02-cross-sectional-momentum.md)
Also essential: [Risk, Psychology, Taxes & Combining the Three →](04-risk-psychology-and-portfolio.md)

<sub>Educational material only; not investment advice. Trading futures involves substantial
risk of loss, including more than your deposit. Figures are approximate and drawn from
published research; verify independently.</sub>
