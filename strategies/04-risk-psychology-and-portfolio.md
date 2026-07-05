# Module 4 — Risk, Psychology, Taxes & Combining the Three (read this one twice)

The first three modules teach *how* each strategy works. This one teaches *why most people who
know how still lose* — and how to be the exception. **Behavioral failure is arguably the #1
real-world cause of loss**, ahead of any flaw in the strategy itself. Do not skip it.

---

## 1. The tail-risk gallery — make the downside *visceral* before you feel it

Numbers like "−34% drawdown" are abstract until you attach a story. Memorize these. Each one
turned confident traders into cautionary tales.

| Event | What happened | The lesson |
|-------|---------------|------------|
| **2009 momentum crash** | As the market bottomed in March 2009, the beaten-down "loser" stocks rocketed off the floor while defensive "winners" lagged. The academic winners-minus-losers (WML) factor **lost roughly −74% in a few months.** | Cross-sectional momentum has **negative skew** — it detonates in the sharp bear-to-bull transition. This is why the [absolute/trend overlay](02-cross-sectional-momentum.md) and volatility-scaling exist. |
| **Feb 2018 "Volmageddon"** | A one-day VIX spike destroyed the short-volatility trade: the **XIV inverse-vol note fell ~97% overnight and was terminated.** Naked and leveraged option sellers were wiped out. | Short-vol / [VRP selling](03-volatility-risk-premium.md) can erase years of steady gains in a *single session.* Never naked, never oversized, always defined-risk. |
| **March 2020 (COVID)** | A fast, violent crash. Short-vol sellers took their worst losses *simultaneously with* their stock portfolios. Trend following's fast **V-shaped snapback** whipsawed many systems. | Short-vol losses **coincide** with equity crashes (it is not a hedge). Trend following's natural enemy is the sharp reversal — expect it, don't "fix" the system after one. |
| **Trend following's 2009–2018 "lost decade"** | The SG Trend Index was essentially **flat for ~9 years** while stocks soared. Assets and traders bled out and quit — right before 2022's +27% year. | The killer here isn't drawdown *depth*, it's **drawdown duration.** The length of underperformance is what breaks people. |
| **The retail day-trader base rate** | In studied markets, roughly **80–97% of persistent day traders lose money**; in Taiwan <1% were reliably profitable net of fees. | The strategies in this guide are the *evidence-backed exceptions*, and even they are modest. Most active trading is a wealth-transfer *away* from the impatient. |

**The pattern in all of them:** the strategy didn't fail — the *person* failed, by over-sizing,
using leverage into a tail, or abandoning a sound system at the point of maximum pain.

## 2. Leverage — the one prescriptive section (two of the three strategies embed it)

Leverage is the mechanism behind nearly every blow-up. Managed futures inherently run *notional
≫ capital*; option selling embeds leverage through margin. Concrete, non-negotiable rules:

- **Never sell naked options.** Always buy the protective wing. This alone removes the classic
  account-ender.
- **Futures and CFDs can lose MORE than you deposited.** A margin call forces liquidation at the
  worst possible moment. Keep a cash cushion large enough that a bad *week* never forces a sale.
- **If you cannot state your true notional leverage right now, you are over-leveraged.** Compute
  notional exposure ÷ account equity for every open position, summed.
- **Size to survive the tail, not to maximize the average.** The math below (§3) shows why.
- **Every increment of extra yield is bought with a fatter left tail.** Bigger size, tighter
  strikes, 0DTE, more leverage — all the same trade: more return in calm times, more ruin in the
  tail. If your return target requires any of them, **lower the target.**

## 3. Position sizing & risk of ruin — the math that keeps you alive

**Fixed-fractional sizing** is the backbone: risk a small, constant fraction of *current* equity
per trade (typically **0.25%–1%** for these strategies), so losses shrink your bet automatically
and no single trade is fatal.

**Why not "bet big to get rich"?** Two reasons, both mathematical:

1. **Drawdowns compound against you.** A −50% loss requires a **+100% gain** to recover; −80%
   requires **+400%.** Deep drawdowns are near-permanent damage, not temporary dips.
2. **Risk of ruin rises non-linearly with bet size.** Even a *positive-edge* strategy will
   eventually hit a losing streak; if your per-bet risk is large, an ordinary streak ruins you
   before the edge pays off. Halving your bet size cuts ruin probability far more than
   proportionally.

**On the Kelly criterion.** Kelly gives the "optimal growth" bet size, but it assumes a
well-behaved payoff distribution — which **none** of these strategies has. All three are
fat-tailed; two are negatively skewed. Full-Kelly badly *over-*sizes them because it
under-weights the rare catastrophe. **Use fractional Kelly (¼ or less), and in practice a
volatility target plus a hard per-strategy loss budget is a cleaner, more robust governor.**
When in doubt, **size down** — you cannot compound if you blow up.

**A simple layered budget you can adopt today:**
- Per-trade risk: **≤ 1%** of equity.
- Per-strategy "heat" (sum of simultaneous open risk / max-losses): a hard cap, e.g. **10–15%.**
- Pre-set drawdown circuit-breaker per strategy (e.g. **−15% to −25%**) that triggers a *review
  and size-cut*, not a panic liquidation.

## 4. Psychology — the binding constraint

You will not be beaten by the market; you'll be beaten by *you*. Know your enemies:

- **Loss aversion** — losses hurt ~2× as much as equivalent gains feel good, so you cut winners
  early and hold losers hoping to break even. This is the *exact opposite* of what trend
  following and momentum require ("cut losers fast, let winners run").
- **The disposition effect** — the specific habit of selling winners too soon and clinging to
  losers. It's so universal it's part of *why* momentum works — don't be on the losing side of it.
- **Recency bias** — extrapolating the last few months forever. It makes you abandon a sound
  system mid-drawdown ("it's broken now") and pile into a hot one at the top.
- **Overconfidence after a winning streak** — the trigger for the classic short-vol blow-up:
  calm wins → boredom → bigger size → the tail hits the now-oversized book.

**The pain has a different *rhythm* in each strategy — know yours in advance:**
- **Trend following:** many small losses and long *flat* stretches. The pain is **boredom and
  doubt** — "is my edge gone, or is this a normal drawdown?" (You cannot tell in real time — §7.)
- **Cross-sectional momentum:** multi-year *relative* underperformance vs. a simple index, plus
  sudden crash reversals. The pain is **envy and impatience.**
- **VRP selling:** you're *right* ~80% of the time, which breeds complacency — then a single
  event takes it back. The pain is **a rare, sharp shock** after a long calm.

**The defense is structural, not willpower:** pre-commit your rules in writing while calm,
**automate execution** where possible so your mood can't intervene, and size so small that no
single outcome is emotionally overwhelming. Discipline you have to summon *in the moment* will
fail exactly when you need it.

## 5. Journaling & process tracking — how you catch yourself slipping

The trade journal is the single highest-leverage habit. It converts vague "I felt like it" into
data you can audit.

**Log for every trade:** date, instrument, the *rule* that triggered it, size, entry/exit, P&L —
and crucially, **the emotion you felt** ("wanted to take profit early," "wanted to skip this
short," "tempted to add size"). Those notes are the early-warning system for discretion creeping
in.

**Review periodically for:**
- **Rule adherence** — did you follow the written plan, yes/no, *separate from* whether the trade
  won? A rule-following loss is a *good* trade; a rule-breaking win is a *bad* one (it reinforces
  a habit that will eventually cost you).
- **Process vs. outcome** — judge decisions by the information available *at the time*, not by how
  they happened to turn out.
- **Realized vs. backtest tracking error** — is your live result drifting from what the strategy
  "should" do? If so, is it the regime, or is it *you* deviating?
- **Your worst loss vs. average win** — especially for VRP, keep this ratio in front of you so
  the asymmetry never surprises you.

**Pre-commit your rules in writing** as a one-page trading plan (universe, signal, sizing, exits,
drawdown protocol, abandonment criteria). Treat any change as a *dated, deliberate decision* —
never an in-the-moment reaction.

## 6. Combining the three — the sophisticated payoff (long-vol vs short-vol)

This is the most valuable insight in the whole guide, and most beginners miss it:

- **Trend following is LONG volatility / long convexity** — positive skew, it *pays off* in
  prolonged crises (crisis alpha).
- **VRP selling is SHORT volatility** — negative skew, it *loses* in crises.
- **They are near-opposite exposures.** Held together and sized sanely, trend following's crisis
  gains partially offset VRP's crisis losses — the two smooth each other's worst months. This is
  genuine, structural diversification, not just "owning more stuff."
- **Cross-sectional momentum** is largely an *equity* exposure with its own crash tail; it
  correlates more with your stock core, so size it as an equity *tilt*, not a diversifier.

**Portfolio construction principles:**
- Treat all three as **small satellite sleeves around a low-cost index/bond core** — not as your
  whole portfolio. Typical starting sleeve sizes might be single-digit to low-double-digit
  percentages *each*, so the worst realistic *combined* case is survivable.
- **Diversify within** each strategy too — a trend book needs 30+ markets; a VRP book needs
  laddered expiries; a momentum book needs enough names.
- **Size so the simultaneous worst case is survivable.** Ask: "If trend is flat, momentum is in a
  drawdown, *and* VRP takes a tail loss in the same quarter, is my total portfolio still fine?"
  If not, the sleeves are too big.
- **Rebalance on a schedule**, mechanically, back toward target weights.

## 7. Epistemic humility — you cannot tell "decayed" from "normal drawdown" in real time

This is the hardest truth in quantitative trading. When a strategy is 18 months into a drawdown,
there is **no clean statistical test** that tells you whether the edge has permanently decayed or
whether you're simply in a normal-but-painful patch. Both look identical from inside.

Consequences you must accept before you start:
- **Assume every backtest is optimistic.** Published anomaly returns fall **~26% out-of-sample**
  and **~58% post-publication** (McLean-Pontiff); roughly two-thirds of anomalies fail careful
  replication (Hou-Xue-Zhang). Deflate every headline number.
- **Benchmarks flatter reality.** CTA/managed-futures indices carry survivorship and backfill
  bias; the "positive every decade since the 1880s" trend record is a *reconstructed simulation*
  with assumed costs — **not** a live track record. Live CTA net returns have been mediocre for
  much of the last ~15 years.
- **Regimes change structurally.** Much of trend following's historical crisis payoff came from a
  40-year *bond bull market* (falling rates) that may not repeat.
- **The only real defense: decide your abandonment criteria *before* you start**, in writing. "I
  will run this for N years / until a drawdown exceeds X% *and* it diverges from the professional
  benchmark by Y" — pre-committed, so the decision to quit is a *rule*, not a panic.

## 8. If you build your OWN rules — don't fool yourself

The "assume backtests are optimistic" warning applies **double** to a backtest *you* built,
because you'll unconsciously curve-fit until the equity curve looks great.

- **Walk-forward / out-of-sample testing:** optimize on one period, validate on a *later,
  untouched* period. If it only works in-sample, it doesn't work.
- **Parameter sensitivity:** a robust rule works across a *range* of parameters (any 6–12 month
  lookback, any 45–55 day crossover). If your result collapses when you change 200-day to 190-day,
  you found noise, not an edge.
- **Deflate for the number of variants you tried.** Testing 100 rule variants and reporting the
  best one is how you manufacture a fake edge (Bailey-López de Prado). The more you searched, the
  more you should discount the winner.
- **Prefer simple, round-number, economically-motivated rules** over finely-tuned ones. Simplicity
  survives; over-optimization is a backtest that already knows the answers.

## 9. Costs, taxes & the boring stuff that decides your net return

**Costs are the decisive killer, and they scale with turnover.** Spreads, commissions, slippage,
market impact, short-borrow/locate fees, and taxes routinely turn a positive *gross* backtest into
a negative *net* result. Options add wide bid/ask spreads; futures and CFDs add leverage.

**Taxes (US — this is nuanced, and it cuts both ways):**
- **Section 1256 contracts** — futures, and **broad-based index options like SPX / XSP / /ES** —
  get **60% long-term / 40% short-term** blended treatment with year-end mark-to-market,
  *regardless of holding period*. This is a genuine **tax advantage** for trend following and
  index-based VRP selling, and it's a real reason to prefer SPX/XSP over SPY.
- **Cross-sectional equity momentum is tax-*inefficient*** — its monthly rebalance generates
  **short-term** capital gains taxed at your ordinary rate. Favor longer cadence, rank buffers,
  and tax-advantaged accounts (IRA/401k) for this one.
- **Also watch:** K-1 forms from some managed-futures partnerships (extra paperwork), wash-sale
  rules on stock/ETF momentum, and general rebalance tax drag.
- **This is US-specific.** Elsewhere, vehicle availability and tax treatment differ (UCITS funds
  vs. US ETFs, different options-approval regimes, no Section 1256). Confirm your local rules.

**Vehicle fees are real:** "cheap" managed-futures ETFs still charge ~0.85–1.5%; some CTAs charge
2-and-20; PutWrite ETFs have trailed the CBOE index due to fees/tracking. Net-of-fee already
erodes an already-low ~0.4–0.6 Sharpe — always model the *net* number.

## 10. Minimum viable capital & who this is realistically NOT for

Be honest about whether you can actually run these:
- **Trend following (DIY futures):** you need enough capital to hold a *diversified* book at
  proper small risk. Even with micro futures, realistically **~$25k–$50k+** to diversify across
  enough markets; below that, use a **managed-futures ETF** sleeve instead of trading futures
  yourself.
- **Cross-sectional momentum:** the most accessible — a few thousand dollars and fractional-share
  ETFs work, though costs/taxes bite small accounts harder.
- **VRP selling:** requires broker **options approval** (spread/level-3), and small accounts can't
  absorb per-contract commissions or size spreads properly. XSP helps; sub-$10k accounts struggle
  to run it mechanically.
- **Blunt truth:** a **sub-$5–10k account** realistically cannot run any of these *mechanically*
  with proper diversification and sizing. For small accounts, the honest move is a low-cost index
  core plus, at most, a small factor-ETF tilt — not DIY futures or options selling.

## 11. Operational & counterparty risk (the stuff nobody warns beginners about)

- **Options assignment / early-exercise / pin risk** — avoided with European, cash-settled
  SPX/XSP; a real hazard with American-style SPY.
- **Overnight gaps through your short strikes** — the market can leap past your levels while you
  sleep; defined-risk caps this, naked does not.
- **Broker/counterparty failure** — futures brokers *have* failed (MF Global). Use reputable,
  well-capitalized brokers.
- **Liquidity evaporation in the tail** — spreads blow out and fills get ugly *exactly* during the
  crises these strategies are exposed to. Assume execution is worst when you most need it.

---

## The bottom line

Every strategy in this guide is real, published, and modest. **Live Sharpe ~0.4–0.6 translates
to roughly mid-single-digit annualized returns with 15%+ drawdowns and multi-year flat periods** —
a world away from the "+1,600%" numbers marketers sell. The edge is not in *knowing* the
strategies (this guide gave you that in an afternoon); it's in the *unglamorous execution*:
sizing so no event can ruin you, following written rules through the ugly stretches, journaling
honestly, and treating these as small satellites around a cheap index core.

**The single most common real-world failure is not a bad strategy — it's a human one:** abandoning
a sound rules-based system at the point of maximum drawdown, over-sizing, or overriding the rules.
Master *that*, and you're already ahead of the ~80–97% who don't.

---

**Back to:** [Overview & Top 3 ←](../README.md) · [Glossary →](glossary.md)

<sub>Educational material only; not investment, tax, or legal advice. Consult a licensed
professional for your specific situation. Trading involves substantial risk of loss.</sub>
