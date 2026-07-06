"""KA-4 (§4, added in slice 4.4): the 2022 MES daily walkthrough.

The 55-bar / 3xATR(20) system on real 2022 MES daily data must produce three
SHORT trades (late-Feb, late-Apr, late-Sep entries, each within +/-3 bars),
P&L signs (-, +, -), and one winner ~2x the average loser. Any deviation is an
engine-or-data bug to investigate BEFORE proceeding (the plan's words).

DATA-GATED: requires data/curated/MES/continuous_1day.parquet from the slice
4.1 pipeline, which is behind the IBKR owner items (§6). The test SKIPS (not
passes) until that file exists — G3's KA-4 acceptance stays open, honestly.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from qt.backtest.engine import Engine, EngineConfig
from qt.backtest.events import Bar
from qt.config import InstrumentsConfig, RiskConfig, StrategiesConfig, load_config
from qt.costs.model import CostModel
from qt.strategies.s1_trend_breakout import S1TrendBreakout
from qt.validation.trades import round_trips

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CURATED = REPO_ROOT / "data" / "curated" / "MES" / "continuous_1day.parquet"
CASH = 10_000_000  # $100k
ENTRY_WINDOWS = [  # late-Feb, late-Apr, late-Sep 2022, +/-3 trading days
    (date(2022, 2, 17), date(2022, 3, 2)),
    (date(2022, 4, 20), date(2022, 5, 4)),
    (date(2022, 9, 15), date(2022, 9, 29)),
]
WINNER_TO_AVG_LOSER = 2.0
WINNER_RATIO_TOLERANCE = 0.8  # "one winner ~ 2x average loser"


@pytest.fixture(scope="module")
def bars_2022() -> list[Bar]:
    if not CURATED.is_file():
        pytest.skip(
            "KA-4 needs curated 2022 MES daily data (slice 4.1 pipeline); "
            "blocked on §6 owner items: IBKR paper login + market-data subscription"
        )
    df = pl.read_parquet(CURATED).filter(
        (pl.col("ts") >= datetime(2021, 6, 1, tzinfo=UTC))
        & (pl.col("ts") <= datetime(2023, 1, 15, tzinfo=UTC))
    )
    return [
        Bar(
            ts=r["ts"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
        )
        for r in df.sort("ts").iter_rows(named=True)
    ]


def test_ka4_2022_mes_walkthrough(bars_2022: list[Bar], config_dir: Path) -> None:
    instruments = load_config(config_dir / "instruments.yaml", InstrumentsConfig)
    risk = load_config(config_dir / "risk.yaml", RiskConfig)
    strategies = load_config(config_dir / "strategies.yaml", StrategiesConfig)
    params = strategies.s1_trend_breakout.tf_d.model_copy(update={"symbols": ["MES"]})
    spec = instruments.instruments["MES"]
    strategy = S1TrendBreakout(params, risk, {"MES": (spec.dollars_per_point, spec.tick_size)})
    result = Engine({"MES": bars_2022}, strategy, CostModel(instruments), EngineConfig(CASH)).run()

    shorts = [f for f in result.fills if f.reason == "target" and f.quantity < 0]
    entries_2022 = [f.ts.date() for f in shorts if f.ts.year == 2022]
    matched = [any(lo <= entry <= hi for entry in entries_2022) for lo, hi in ENTRY_WINDOWS]
    assert all(matched), f"expected short entries in {ENTRY_WINDOWS}, got {entries_2022}"

    trades = round_trips(result.fills, CostModel(instruments))
    trades_2022 = trades[-3:]  # the three walkthrough trades
    signs = [t > 0 for t in trades_2022]
    assert signs == [False, True, False], f"expected (-, +, -), got {trades_2022}"

    winner = max(trades_2022)
    losers = [abs(t) for t in trades_2022 if t < 0]
    avg_loser = sum(losers) / len(losers)
    ratio = winner / avg_loser
    assert abs(ratio - WINNER_TO_AVG_LOSER) <= WINNER_RATIO_TOLERANCE, (
        f"winner/avg-loser ratio {ratio:.2f} not ~2x"
    )
