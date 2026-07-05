# Glossary — every term in this guide, defined plainly

Terms are grouped by topic. Bold terms link conceptually to the strategy modules where they matter
most.

## General trading & risk

- **Active vs. passive** — *Active* trading makes ongoing buy/sell decisions to beat or diversify
  a benchmark; *passive* just holds a broad index. This guide teaches *active* strategies with the
  best evidence, while noting passive indexing is the default for most people.
- **Alpha** — return above what you'd expect for the risk taken; genuine skill/edge, as opposed to
  just being exposed to the market.
- **Backtest** — simulating a strategy on historical data. Useful for understanding a strategy's
  *character*, dangerous as a return promise — real results are almost always worse.
- **Sharpe ratio** — return per unit of volatility (risk-adjusted return). Higher is better, but it
  **flatters negatively-skewed strategies** because it treats a rare catastrophe the same as normal
  wobble. Classic factors: market ~0.4, momentum ~0.7 in-sample; these strategies live at ~0.3–0.6.
- **Drawdown** — the peak-to-trough decline in your account. Two dimensions matter: **depth** (how
  far down) and **duration** (how long — often the thing that actually breaks people).
- **Skew** — the asymmetry of returns. **Positive skew** = many small losses, rare big wins (trend
  following). **Negative skew** = many small wins, rare big losses (VRP selling, *and* momentum).
- **Volatility** — how much returns fluctuate; the standard risk measure. *Realized* = measured
  after the fact; *implied* = priced into options.
- **Risk of ruin** — the probability of losing enough to be knocked out. Rises non-linearly with
  bet size; the reason to size small.
- **Fixed-fractional sizing** — risking a constant small % of *current* equity per trade, so losses
  automatically shrink your next bet.
- **Kelly criterion** — the theoretically "optimal growth" bet size; badly over-sizes fat-tailed,
  skewed strategies. Use *fractional* Kelly (¼ or less), or a volatility target instead.
- **Expectancy** — average profit per trade over many trades = (win% × avg win) − (loss% × avg
  loss). You must think in expectancy across hundreds of trades, never trade-by-trade.
- **Whipsaw** — a false signal that reverses right after you act, producing a small loss. The
  normal cost of trend/breakout systems.
- **R / R-multiple** — a trade's result expressed in units of the amount you risked. Risk $900,
  make $3,000 → +3.3R. Lets you compare trades of different sizes.
- **Slippage** — the difference between the price you expected and the price you got; worst in fast
  or illiquid markets.
- **Survivorship / backfill bias** — indices and databases that drop failures (survivorship) or
  add managers' good early history retroactively (backfill) look better than reality.

## Momentum & trend following

- **Momentum** — the tendency of recent performance to persist over months. The most robust anomaly
  in finance.
- **Cross-sectional momentum** — ranking assets *against each other* and holding the relative
  winners ([Strategy 2](02-cross-sectional-momentum.md)).
- **Time-series momentum (TSMOM)** — comparing each asset to *its own* past; the basis of trend
  following ([Strategy 1](01-trend-following.md)). Can be long some markets, short others, or in
  cash.
- **Relative strength** — another name for cross-sectional momentum ranking.
- **The "skip month" / "12-1"** — ranking on returns from 12 months ago to *1 month ago*, excluding
  the most recent month to avoid short-term reversal noise.
- **Formation / lookback period** — the trailing window used to measure momentum (typically 3–12
  months).
- **Holding / rebalance period** — how long you hold before re-ranking (typically 1–6 months).
- **Managed futures / CTA** — the industry/regulatory label for professional trend-following futures
  programs. "CTA" = Commodity Trading Advisor.
- **Momentum crash** — the signature negative-skew failure of cross-sectional momentum: after a
  market bottom, avoided "losers" rebound violently while held "winners" lag (WML lost ~−74% in
  2009).
- **Crisis alpha** — trend following's tendency to profit during *protracted* equity bear markets,
  because those are trends it rides short. Conditional on the crisis being slow enough for trends to
  form.
- **Convexity / "long volatility"** — a return profile like owning options/insurance: small regular
  costs, rare large payoffs. Trend following has it; VRP selling is the opposite ("short vol").
- **Volatility targeting** — sizing positions so each contributes equal risk and total portfolio
  volatility stays near a constant; you shrink exposure when markets get wild.
- **Absolute / trend overlay** — a gate (e.g. only hold a ranked winner if it's also above its
  200-day MA) that lets a relative strategy sidestep broad bear markets.
- **Donchian channel / breakout** — buying an N-day high / selling an N-day low; the classic
  "Turtle" trend signal.
- **Moving average (SMA/EMA)** — the average price over N days; crossovers (50/200) are a common
  trend signal.
- **ATR (Average True Range)** — a measure of a market's typical daily range; used for volatility-
  based stops and position sizing.
- **Chandelier stop** — a trailing stop set at the highest-high-since-entry minus a multiple of ATR;
  ratchets up, never down.
- **Back-adjusted / continuous futures** — a stitched-together price series across expiring futures
  contracts, needed so signals aren't broken by expiration.
- **Roll / roll yield** — moving a futures position to the next contract before expiry; the price
  difference between contracts (contango vs. backwardation) creates a cost or benefit.
- **Notional vs. margin** — *notional* is the full value of the position you control; *margin* is
  the smaller cash you post. Their ratio is your leverage.

## Options & the Volatility Risk Premium

- **Implied volatility (IV)** — the market's priced-in expectation of future movement, embedded in
  option prices. Higher IV = richer premiums.
- **Realized volatility (RV)** — how much the underlying actually moved, measured after the fact.
- **Volatility / Variance Risk Premium (VRP)** — the persistent gap where IV averages *above*
  subsequent RV (~3–4 points on the S&P). The structural edge behind [Strategy 3](03-volatility-risk-premium.md);
  a *carry*, not a timing signal.
- **VIX** — the market's 30-day implied-volatility index for the S&P 500 (the "fear gauge").
- **IV Rank / IV Percentile** — where current IV sits within its own trailing 1-year range; sellers
  prefer higher.
- **The Greeks:**
  - **Delta** — sensitivity to a $1 move in the underlying; also ~probability of finishing
    in-the-money (a 16-delta short put ≈ 84% chance of expiring worthless).
  - **Theta** — daily time-decay; what an option *seller* harvests.
  - **Gamma** — how fast delta changes; risk explodes in the final ~2 weeks before expiry.
  - **Vega** — sensitivity to IV changes; a net seller is *short vega* and loses when IV spikes.
- **DTE (Days To Expiration)** — time left on an option; the selling sweet spot is ~30–60 DTE.
- **Put credit spread** — sell a put and buy a further-OTM put as a protective wing; **defined
  risk** (max loss = strike width − credit). The recommended core VRP trade.
- **Cash-secured put (CSP)** — sell a put backed by enough cash to buy the shares if assigned; fully
  collateralized but still large downside below the strike.
- **Naked / uncovered put** — selling a put with no wing and less than full cash; **undefined,
  catastrophic downside — the account-ender. Don't.**
- **Probability of Profit (POP)** — the modeled chance a trade makes money; **hides** that each
  loser can be several times a winner. Always pair with win/loss *size*.
- **Assignment / early exercise / pin risk** — the risk of being forced to buy/sell shares on an
  option; avoided with European, cash-settled index options.
- **Section 1256 contracts** — futures and broad-based index options (SPX/XSP/ES); taxed 60%
  long-term / 40% short-term regardless of holding period (a US tax advantage).
- **0DTE** — options expiring the same day; very high gamma risk. A yield-chasing trap for premium
  sellers.
- **"Picking up pennies in front of a steamroller"** — the folk description of naive premium
  selling: steady small gains until a rare event flattens you.
- **Portfolio heat / Buying Power Reduction (BPR)** — how much of your capital/risk is committed;
  for short-vol, the *sum* of max-losses across all positions (because they all lose together in a
  crash).

## Behavioral & meta

- **Loss aversion** — losses hurt ~2× as much as equal gains feel good; drives cutting winners early
  and holding losers.
- **Disposition effect** — the specific tendency to sell winners too soon and hold losers too long.
- **Recency bias** — over-weighting the recent past; makes people abandon systems mid-drawdown and
  chase hot ones at the top.
- **Alpha decay / crowding** — published edges shrink as more capital chases them (~26% lower
  out-of-sample, ~58% lower post-publication).
- **Walk-forward / out-of-sample testing** — validating a strategy on data it wasn't tuned on;
  the defense against curve-fitting.
- **Overfitting / curve-fitting** — tuning a strategy so precisely to past data that it captures
  noise and fails live.

---

**Back to:** [Overview & Top 3 ←](../README.md)
