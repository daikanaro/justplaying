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
from qt.backtest.events import Bar, FillEvent
from qt.config import InstrumentsConfig, RiskConfig, StrategiesConfig, load_config
from qt.costs.model import CostModel
from qt.strategies.s1_trend_breakout import S1TrendBreakout

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CURATED = REPO_ROOT / "data" / "curated" / "MES" / "continuous_1day.parquet"
# $10M: at $100k the §1 budget (risk fraction x equity) is smaller than one
# MES contract's 3xATR(20) stop risk on 2022 vol, so sizing floors to ZERO and
# the walkthrough silently produces no trades. KA-4 checks signal/exit
# mechanics, not account scale.
CASH = 1_000_000_000
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


def _episodes(fills: list[FillEvent], costs: CostModel) -> list[tuple[date, bool, int]]:
    """(entry date, is_short, net cents) per flat-to-flat episode, in close
    order. Single symbol, single lot per episode (S1 never scales in);
    reversal fills split into close + fresh entry, exactly like
    qt.validation.trades.round_trips. Open at stream end = not an episode."""
    out: list[tuple[date, bool, int]] = []
    position = 0
    entry_date: date | None = None
    entry_ticks = 0
    pnl = 0
    for fill in fills:
        tick_value = costs.spec(fill.symbol).tick_value_cents
        ticks = costs.price_to_ticks(fill.symbol, fill.price)
        quantity = fill.quantity
        per_contract = fill.commission_cents // abs(quantity)
        while quantity != 0:
            if position == 0:
                entry_date, entry_ticks = fill.ts.date(), ticks
                pnl = -per_contract * abs(quantity)
                position, quantity = quantity, 0
            elif (position > 0) != (quantity > 0):
                direction = 1 if position > 0 else -1
                closed = min(abs(quantity), abs(position))
                pnl += (ticks - entry_ticks) * tick_value * direction * closed
                pnl -= per_contract * closed
                position -= direction * closed
                quantity += direction * closed
                if position == 0 and entry_date is not None:
                    out.append((entry_date, direction < 0, pnl))
            else:
                msg = "unexpected scale-in fill in the KA-4 walkthrough"
                raise AssertionError(msg)
    return out


def test_ka4_2022_mes_walkthrough(bars_2022: list[Bar], config_dir: Path) -> None:
    instruments = load_config(config_dir / "instruments.yaml", InstrumentsConfig)
    risk = load_config(config_dir / "risk.yaml", RiskConfig)
    strategies = load_config(config_dir / "strategies.yaml", StrategiesConfig)
    params = strategies.s1_trend_breakout.tf_d.model_copy(update={"symbols": ["MES"]})
    spec = instruments.instruments["MES"]
    strategy = S1TrendBreakout(params, risk, {"MES": (spec.dollars_per_point, spec.tick_size)})
    result = Engine({"MES": bars_2022}, strategy, CostModel(instruments), EngineConfig(CASH)).run()

    episodes = _episodes(result.fills, CostModel(instruments))
    shorts_2022 = [e for e in episodes if e[0].year == 2022 and e[1]]
    assert len(shorts_2022) == 3, (
        f"expected exactly 3 short trades entered in 2022, got {shorts_2022}"
    )

    # Tie each plan window to ITS trade — exactly one, and it must be short.
    walkthrough: list[int] = []
    for lo, hi in ENTRY_WINDOWS:
        in_window = [e for e in episodes if lo <= e[0] <= hi]
        assert len(in_window) == 1, f"expected exactly one entry in [{lo}, {hi}], got {in_window}"
        entry_day, is_short, pnl = in_window[0]
        assert is_short, f"trade entered {entry_day} is long, expected short"
        walkthrough.append(pnl)

    signs = [t > 0 for t in walkthrough]
    assert signs == [False, True, False], f"expected (-, +, -), got {walkthrough}"

    winner = max(walkthrough)
    losers = [abs(t) for t in walkthrough if t < 0]
    avg_loser = sum(losers) / len(losers)
    ratio = winner / avg_loser
    assert abs(ratio - WINNER_TO_AVG_LOSER) <= WINNER_RATIO_TOLERANCE, (
        f"winner/avg-loser ratio {ratio:.2f} not ~2x"
    )
