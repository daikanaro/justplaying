#!/usr/bin/env python3
"""Cross-sectional momentum backtest template (teaching tool).

Implements the exact strategy taught in strategies/02-cross-sectional-momentum.md:

  * Universe: any set of tickers (default: the 11 S&P sector SPDRs)
  * Signal:   12-1 momentum  = price 1 month ago / price 12 months ago - 1
              (the "skip month" avoids short-term reversal noise)
  * Filter:   absolute/trend gate -- only hold a winner whose 12-1 return is
              positive AND whose price is above its 200-day moving average;
              failed slots sit in cash
  * Hold:     top N by signal, equal weight, rebalanced monthly
  * Risk:     optional portfolio volatility targeting (scale exposure down
              when trailing realized vol runs above target; never levered)
  * Costs:    per-trade cost in basis points applied to turnover

The point of this template is NOT to find the best parameters. It is to let
you SEE, on real or synthetic data, the multi-year droughts, the 20-35%
drawdowns, and how much costs and cadence matter -- before real money is
at stake. Resist the urge to optimize: robust round-number defaults beat a
curve-fit backtest that already knows the answers.

Usage:
  python3 momentum_backtest.py --demo                # synthetic data, offline
  python3 momentum_backtest.py --yahoo               # 11 sector SPDRs via yfinance
  python3 momentum_backtest.py --csv-dir ./data      # your own CSVs (Date,Close)
  python3 momentum_backtest.py --yahoo --top 3 --vol-target 12 --cost-bps 10

CSV format: one file per ticker named <TICKER>.csv with columns Date,Close
(adjusted/total-return close strongly preferred -- dividends matter).
"""

import argparse
import sys

import numpy as np
import pandas as pd

SECTOR_SPDRS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]


# --------------------------------------------------------------------------- data

def load_demo(years: int = 18, n_assets: int = 11, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily closes: a common market factor with drift regimes and
    occasional crashes, plus idiosyncratic noise per asset. Good enough to
    exercise every code path offline and show realistic-looking equity curves.
    """
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2007-01-02", periods=years * 252)
    n = len(days)

    # Market factor: drift regime flips roughly every 2 years; two crash episodes.
    regime_len = 2 * 252
    drifts = rng.choice([0.10, 0.06, -0.04, 0.14], size=n // regime_len + 1)
    mkt_mu = np.repeat(drifts, regime_len)[:n] / 252
    mkt = mkt_mu + 0.16 / np.sqrt(252) * rng.standard_normal(n)
    for crash_start in (int(n * 0.30), int(n * 0.72)):          # two bear episodes
        mkt[crash_start : crash_start + 60] -= 0.45 / 60        # -45% over ~3 months
        mkt[crash_start + 60 : crash_start + 90] += 0.20 / 30   # sharp partial snapback

    prices = {}
    for i in range(n_assets):
        beta = rng.uniform(0.6, 1.4)
        idio_vol = rng.uniform(0.10, 0.22) / np.sqrt(252)
        # Sector-specific slow-moving drift so relative leadership rotates.
        sector_mu = np.repeat(rng.normal(0.02, 0.06, size=n // regime_len + 1), regime_len)[:n] / 252
        r = beta * mkt + sector_mu + idio_vol * rng.standard_normal(n)
        prices[f"SEC{i + 1:02d}"] = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame(prices, index=days)


def load_yahoo(tickers: list[str], start: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance not installed. Run: pip install yfinance  (or use --demo / --csv-dir)")
    px = yf.download(tickers, start=start, auto_adjust=True, progress=False)["Close"]
    return px.dropna(how="all").ffill().dropna()


def load_csv_dir(path: str) -> pd.DataFrame:
    import glob
    import os

    frames = {}
    for f in sorted(glob.glob(os.path.join(path, "*.csv"))):
        name = os.path.splitext(os.path.basename(f))[0].upper()
        df = pd.read_csv(f, parse_dates=["Date"], index_col="Date")
        frames[name] = df["Close"]
    if not frames:
        sys.exit(f"No CSVs found in {path} (expected <TICKER>.csv with Date,Close columns)")
    return pd.DataFrame(frames).sort_index().ffill().dropna()


# ----------------------------------------------------------------------- backtest

def run_backtest(
    prices: pd.DataFrame,
    top_n: int = 3,
    lookback_m: int = 12,
    skip_m: int = 1,
    ma_days: int = 200,
    cadence_m: int = 1,
    vol_target: float = 12.0,   # annualized %, 0 disables
    vol_window: int = 60,       # trading days used to estimate realized vol
    cost_bps: float = 10.0,     # per unit traded
    cash_rate: float = 2.0,     # annualized % earned on the cash sleeve
) -> dict:
    daily_ret = prices.pct_change().fillna(0.0)
    month_end = prices.resample("ME").last()
    ma = prices.rolling(ma_days).mean() if ma_days else None

    # Signal at month t uses only data available at t (no lookahead):
    # momentum = P[t - skip] / P[t - lookback] - 1
    momentum = month_end.shift(skip_m) / month_end.shift(lookback_m) - 1

    weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    cash_w = pd.Series(1.0, index=prices.index)
    rebal_dates = month_end.index[lookback_m::cadence_m]

    current_w = pd.Series(0.0, index=prices.columns)
    current_cash = 1.0
    last_sig = None
    turnover_log = []

    for t in prices.index:
        # Rebalance on the first trading day AFTER a signal month-end
        # (signal computed at month-end close, traded the next day -- no lookahead).
        due = [d for d in rebal_dates if d < t]
        if due and due[-1] != last_sig:
            sig_date = last_sig = due[-1]
            scores = momentum.loc[sig_date].dropna()

            # Absolute/trend gate: positive own momentum AND above the 200d MA.
            eligible = scores[scores > 0]
            if ma is not None:
                ma_row = ma.asof(sig_date)
                px_row = prices.asof(sig_date)
                eligible = eligible[(px_row[eligible.index] > ma_row[eligible.index]).fillna(False)]

            picks = eligible.nlargest(top_n).index
            base_w = pd.Series(0.0, index=prices.columns)
            if len(picks):
                base_w[picks] = 1.0 / top_n  # unfilled slots stay in cash

            # Volatility targeting: scale the whole book down when the
            # would-be portfolio has been running hotter than target.
            scalar = 1.0
            if vol_target > 0 and len(picks):
                hist = daily_ret.loc[:sig_date, picks].tail(vol_window)
                realized = hist.mean(axis=1).std() * np.sqrt(252) * 100
                if realized > 0:
                    scalar = min(1.0, max(0.3, vol_target / realized))

            new_w = base_w * scalar
            traded = (new_w - current_w).abs().sum() + abs((1 - new_w.sum()) - current_cash)
            turnover_log.append(traded / 2)  # one-way turnover
            current_w, current_cash = new_w, 1 - new_w.sum()

        weights.loc[t] = current_w
        cash_w.loc[t] = current_cash

    # Portfolio daily returns; costs charged on rebalance days via turnover.
    strat_ret = (weights.shift(1) * daily_ret).sum(axis=1) + cash_w.shift(1).fillna(1.0) * (cash_rate / 100 / 252)
    w_change = weights.diff().abs().sum(axis=1)
    strat_ret -= w_change * (cost_bps / 1e4)

    bench_ret = daily_ret.mean(axis=1)  # equal-weight buy & hold of the universe
    return {
        "strategy": (1 + strat_ret).cumprod(),
        "benchmark": (1 + bench_ret).cumprod(),
        "strat_ret": strat_ret,
        "bench_ret": bench_ret,
        "avg_annual_turnover": float(np.mean(turnover_log)) * (12 / cadence_m) if turnover_log else 0.0,
    }


# -------------------------------------------------------------------------- stats

def stats(equity: pd.Series, ret: pd.Series, cash_rate: float) -> dict:
    yrs = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = equity.iloc[-1] ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(252)
    sharpe = (ret.mean() * 252 - cash_rate / 100) / vol if vol > 0 else float("nan")
    dd = equity / equity.cummax() - 1
    yearly = (1 + ret).groupby(ret.index.year).prod() - 1
    return {
        "CAGR": f"{cagr:8.2%}",
        "Ann. vol": f"{vol:8.2%}",
        "Sharpe": f"{sharpe:8.2f}",
        "Max drawdown": f"{dd.min():8.2%}",
        "Worst year": f"{yearly.min():8.2%}",
        "Best year": f"{yearly.max():8.2%}",
        "% positive years": f"{(yearly > 0).mean():8.2%}",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo", action="store_true", help="synthetic data (offline, reproducible)")
    src.add_argument("--yahoo", action="store_true", help="download real data via yfinance")
    src.add_argument("--csv-dir", help="directory of <TICKER>.csv files with Date,Close")
    ap.add_argument("--tickers", nargs="+", default=SECTOR_SPDRS, help="tickers for --yahoo")
    ap.add_argument("--start", default="2005-01-01", help="start date for --yahoo")
    ap.add_argument("--top", type=int, default=3, help="hold top N (default 3)")
    ap.add_argument("--lookback", type=int, default=12, help="lookback months (default 12)")
    ap.add_argument("--skip", type=int, default=1, help="skip months (default 1 -- the '12-1')")
    ap.add_argument("--ma", type=int, default=200, help="trend-filter MA days, 0 disables (default 200)")
    ap.add_argument("--cadence", type=int, default=1, help="rebalance every N months (default 1)")
    ap.add_argument("--vol-target", type=float, default=12.0, help="annualized vol target %%, 0 disables")
    ap.add_argument("--cost-bps", type=float, default=10.0, help="cost per unit traded, bps (default 10)")
    ap.add_argument("--cash-rate", type=float, default=2.0, help="annual %% earned on cash (default 2)")
    ap.add_argument("--out", help="write equity curves to this CSV path")
    args = ap.parse_args()

    if args.demo:
        prices = load_demo()
        print("Data: SYNTHETIC (demo mode -- results illustrate mechanics, not history)\n")
    elif args.yahoo:
        prices = load_yahoo(args.tickers, args.start)
        print(f"Data: Yahoo Finance, {len(prices.columns)} tickers, {prices.index[0]:%Y-%m-%d} to {prices.index[-1]:%Y-%m-%d}\n")
    else:
        prices = load_csv_dir(args.csv_dir)
        print(f"Data: {args.csv_dir}, {len(prices.columns)} tickers, {prices.index[0]:%Y-%m-%d} to {prices.index[-1]:%Y-%m-%d}\n")

    res = run_backtest(
        prices, top_n=args.top, lookback_m=args.lookback, skip_m=args.skip,
        ma_days=args.ma, cadence_m=args.cadence, vol_target=args.vol_target,
        cost_bps=args.cost_bps, cash_rate=args.cash_rate,
    )

    s = stats(res["strategy"], res["strat_ret"], args.cash_rate)
    b = stats(res["benchmark"], res["bench_ret"], args.cash_rate)
    name = f"Momentum top-{args.top} ({args.lookback}-{args.skip}, MA{args.ma}, {args.cadence}mo)"
    print(f"{'':22s}{name:>34s}{'Equal-weight B&H':>20s}")
    for k in s:
        print(f"{k:22s}{s[k]:>34s}{b[k]:>20s}")
    print(f"{'Avg annual turnover':22s}{res['avg_annual_turnover']:>33.0%}{'--':>20s}")

    # The drawdown line is the part to actually study.
    eq = res["strategy"]
    dd = eq / eq.cummax() - 1
    print("\nWorst drawdown trough: "
          f"{dd.min():.1%} on {dd.idxmin():%Y-%m-%d}  "
          "(now go look at how LONG the underwater stretches are -- duration breaks people, not depth)")

    if args.out:
        pd.DataFrame({"strategy": res["strategy"], "benchmark": res["benchmark"], "drawdown": dd}).to_csv(args.out)
        print(f"Equity curves written to {args.out}")


if __name__ == "__main__":
    main()
