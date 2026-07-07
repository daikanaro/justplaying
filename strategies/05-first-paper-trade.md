# Module 5 — Your First Paper Trade, Step by Step

This module turns [Strategy 2 — Cross-Sectional Momentum](02-cross-sectional-momentum.md) into
your literal first month of practice. **We start with momentum sector rotation** because it's the
only one of the three you can run with a plain brokerage account — no futures approval, no options
approval, no leverage, and a monthly cadence that fits around a job. (Once this feels boring —
which is the goal — the same staged method applies to the other two strategies.)

**Time required:** ~1 hour to set up, then ~20 minutes once a month.
**Money required:** $0 — this is paper trading. Do not skip the paper stage.

---

## Week 0 — Set up (one hour, once)

1. **Create your tracking sheet.** A spreadsheet is genuinely enough. One tab called `Ranks`,
   one called `Journal`, one called `Plan` (a companion journal template lives at
   [`tools/trade-journal-template.csv`](../tools/trade-journal-template.csv)).
2. **Write the plan — before you look at any prices.** Copy this into the `Plan` tab and treat
   any future change as a dated, deliberate decision:

   > **Universe:** the 11 S&P sector SPDRs — XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC.
   > **Signal:** 12-1 total return (12 months ago → 1 month ago; skip the most recent month).
   > **Hold:** top 3 by signal, equal weight.
   > **Filter:** a top-3 name must ALSO have a positive 12-1 return AND be above its 200-day
   > moving average; failed slots go to "cash" (SGOV).
   > **Rebalance:** last trading day of each month, orders "placed" at the next open.
   > **Paper capital:** $10,000 (pretend).
   > **I will run this for 3 months minimum before changing anything.**

3. **Pick your rebalance day** and put a recurring reminder in your calendar for the last
   trading day of the month. Consistency of timing beats cleverness.
4. **(Optional but recommended) Run the backtest once** so the shape of what you're signing up
   for is in your bones before month one:
   ```
   pip install pandas numpy yfinance
   python3 tools/momentum_backtest.py --yahoo
   ```
   Look at the max drawdown and the worst year. Then run it again with `--ma 0 --vol-target 0`
   and watch the drawdown roughly double — that's what the filter is for.

## Rebalance Day 1 — your first ranking (~20 minutes)

**Step 1 — Get the two prices you need per ticker.** For each of the 11 ETFs you need the
**adjusted close** (dividends included) from ~12 months ago and from ~1 month ago. Easiest
sources: your broker's chart, Yahoo Finance's "Historical Data" tab, or
`python3 tools/momentum_backtest.py --yahoo` which computes ranks implicitly.

**Step 2 — Compute the 12-1 return.** In your `Ranks` tab, one row per ticker:

| Ticker | Price 12mo ago (A) | Price 1mo ago (B) | 12-1 return = B/A − 1 | Above 200d MA? | Rank |
|--------|-----|-----|------|------|------|
| XLK    | 205.10 | 241.87 | **+17.9%** | Yes | 1 |
| …      | | | | | |

Sort descending. Rank 1 = strongest. *(Common error: using today's price as B. Don't — the skip
month exists to dodge short-term reversal noise.)*

**Step 3 — Apply the filter.** For each of the top 3: is the 12-1 return positive? Is the price
above its 200-day moving average (any charting site shows this in two clicks)? Any "no" → that
slot becomes SGOV (cash) instead.

**Step 4 — "Place" the trades.** $10,000 ÷ 3 ≈ $3,333 per slot. Write down, *before the next
open*: ticker, intended dollar amount, and the next day's opening price when it happens. If your
broker has a paper-trading mode (thinkorswim, IBKR, Webull all do), place them there instead —
real order tickets build real reflexes.

**Step 5 — Journal the feeling, not just the trade.** This is the step that separates people who
learn from people who churn. In the `Journal` tab record: date, ranks, what you bought, **and one
honest sentence about what you *wanted* to do instead** ("XLE looks cheap, wanted to grab it";
"XLK feels way too high to buy"). Those sentences are your future edge — they're the exact
impulses that destroy live accounts.

**Step 6 — Close the spreadsheet and do nothing for a month.** No peeking-and-tinkering. The
strategy's edge partly *comes from* not reacting to the daily noise everyone else reacts to.

## Rebalance Day 2 — the part that actually teaches you

Re-run steps 1–5. Now the real lessons arrive:

- **A holding dropped from rank 2 to rank 4.** Plain top-3 rule: sell it, buy the new #3. You'll
  hate selling it if it made money ("it's still fine!") and hate keeping the new one ("I'm buying
  the top!"). Do it anyway; journal the resistance.
- **The sector you refused to buy last month just ripped +11%.** You missed it. That is the
  *normal cost* of momentum, not a flaw. You do not chase it at rank 4 — you buy it only if it
  enters your top 3.
- **Everything fell and half your slots failed the filter.** Then half your book is "in SGOV."
  It will feel like doing nothing. That defensive nothing is the mechanism that dodged 2008.

## After 3 months — score yourself on process, not P&L

Three months of monthly rotation is only 3 data points of *returns* — statistically meaningless.
But it's ~9–12 data points of *process*, which is what you're actually training. Grade:

- [ ] Did I compute ranks on the scheduled day, every time? (no early/late rebalances)
- [ ] Did I take every signal, including ones I hated?
- [ ] Did I sell every drop-out, including winners I liked?
- [ ] Is every journal entry filled in, including the feelings column?
- [ ] Can I state from memory what my max expected drawdown is (20–35%) and my plan when it comes?

**5/5 for three straight months → you've earned the right to go live small** (a 5–10% sleeve of
your investable assets, as [Module 2 §9](02-cross-sectional-momentum.md) describes). Anything
less → run another 3 paper months. There is no deadline; the market will still be there.

## Where the other two strategies fit

- **Trend following:** paper-trade it *after* momentum feels mechanical — the same journaling
  method, but you'll need a futures paper account (most brokers offer one) or simply track a
  managed-futures ETF sleeve (DBMF/KMLM) against the SG Trend Index. See
  [Module 1 §9](01-trend-following.md).
- **VRP selling:** strictly after you have options approval and have read
  [Module 3](03-volatility-risk-premium.md) twice. Your first 20–30 paper spreads are about order
  mechanics (the vertical as one ticket, the 50% profit order, the 21-DTE calendar alarm), not
  P&L. See [Module 3 §9](03-volatility-risk-premium.md).

---

**Back to:** [Overview ←](../README.md) · **Tools:** [`momentum_backtest.py`](../tools/momentum_backtest.py) ·
[`trade-journal-template.csv`](../tools/trade-journal-template.csv)

<sub>Educational material only; not investment advice.</sub>
