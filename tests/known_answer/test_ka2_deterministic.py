"""KA-2 (§4, G2 gate): 10 hand-built bars, hand-computed fills, costs, and
P&L. The engine must match TO THE CENT.

Setup: MES (tick 0.25 = $1.25, commission $0.80/side), all bars at 15:00 UTC
on consecutive weekdays (RTH -> 1 tick slippage), initial cash $100,000.

Script:
- close of bar 0: target +2            -> fills bar 1 open
- close of bar 1: protective stop 4998.00
- bar 3 OPENS at 4996.00, gapping through the stop -> gap-through fill at
  open - slip = 4995.75 (NOT at the stop price)
- close of bar 5: target -1            -> fills bar 6 open
- close of bar 8: target 0             -> covers bar 9 open

Hand computation (integer cents):
  Trade 1 (long 2): entry 5003.00+0.25 = 5003.25; exit 4995.75
    points = 4995.75-5003.25 = -7.50 = -30 ticks
    P&L = -30 x 125c x 2 = -7,500c;  commissions 160c + 160c
  Trade 2 (short 1): entry 4987.00-0.25 = 4986.75; cover 4978.00+0.25 = 4978.25
    points = 4986.75-4978.25 = +8.50 = +34 ticks
    P&L = +34 x 125c x 1 = +4,250c;  commissions 80c + 80c
  Final equity = 10,000,000 - 7,500 - 320 + 4,250 - 160 = 9,996,270c ($99,962.70)
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.backtest.engine import Engine, EngineConfig, StrategyContext
from qt.backtest.events import Bar
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel

CASH = 10_000_000

# Consecutive weekdays: Mon Jul 8 .. Fri Jul 19, 2024 (no holidays), 15:00 UTC.
DAYS = [8, 9, 10, 11, 12, 15, 16, 17, 18, 19]
OHLC = [
    (5000.00, 5005.00, 4995.00, 5002.00),  # 0
    (5003.00, 5010.00, 5000.00, 5008.00),  # 1: entry fill 2 @ 5003.25
    (5008.00, 5012.00, 5004.00, 5006.00),  # 2: stop 4998 live, low 5004 -> no fire
    (4996.00, 5001.00, 4990.00, 4992.00),  # 3: opens THROUGH stop -> fill 4995.75
    (4993.00, 4998.00, 4988.00, 4990.00),  # 4
    (4991.00, 4996.00, 4986.00, 4988.00),  # 5: signal short at close
    (4987.00, 4992.00, 4980.00, 4984.00),  # 6: short fill 1 @ 4986.75
    (4985.00, 4990.00, 4978.00, 4980.00),  # 7
    (4982.00, 4987.00, 4976.00, 4979.00),  # 8: signal flat at close
    (4978.00, 4984.00, 4974.00, 4981.00),  # 9: cover fill 1 @ 4978.25
]

BARS = [
    Bar(
        ts=datetime(2024, 7, day, 15, 0, tzinfo=UTC),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=1000.0,
    )
    for day, (o, h, lo, c) in zip(DAYS, OHLC, strict=True)
]

# Equity after each bar's close, hand-computed (cents):
EXPECTED_EQUITY = [
    10_000_000,  # 0: flat
    10_004_590,  # 1: cash 9,999,840 + unreal (5008-5003.25 = 19 ticks x 125 x 2 = 4,750)
    10_002_590,  # 2: unreal (5006-5003.25 = 11 ticks -> 2,750)
    9_992_180,  # 3: stopped out; cash 9,999,840 - 7,500 - 160
    9_992_180,  # 4: flat
    9_992_180,  # 5: flat (signal only)
    9_993_475,  # 6: cash 9,992,100 + unreal (4986.75-4984 = 11 ticks x 125 = 1,375)
    9_995_475,  # 7: unreal 27 ticks -> 3,375
    9_995_975,  # 8: unreal 31 ticks -> 3,875
    9_996_270,  # 9: covered; cash 9,992,100 + 4,250 - 80
]


class Ka2Strategy:
    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        index = ctx.index
        if index == 1:
            ctx.set_stop("MES", 4998.00)
        if index == 0:
            return {"MES": 2}
        if index in (1, 2):
            return {"MES": 2}
        if index in (5, 6, 7):
            return {"MES": -1}
        return {"MES": 0}


@pytest.fixture(scope="module")
def result(config_dir: Path):  # type: ignore[no-untyped-def]
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    return Engine({"MES": BARS}, Ka2Strategy(), costs, EngineConfig(CASH)).run()


def test_ka2_fill_sequence(result) -> None:  # type: ignore[no-untyped-def]
    assert [(f.quantity, f.price, f.commission_cents, f.reason) for f in result.fills] == [
        (2, 5003.25, 160, "target"),
        (-2, 4995.75, 160, "stop"),  # gap-through: open 4996.00 - 0.25, NOT 4997.75
        (-1, 4986.75, 80, "target"),
        (1, 4978.25, 80, "target"),
    ]


def test_ka2_fill_timing(result) -> None:  # type: ignore[no-untyped-def]
    assert [f.ts for f in result.fills] == [BARS[1].ts, BARS[3].ts, BARS[6].ts, BARS[9].ts]


def test_ka2_equity_curve_to_the_cent(result) -> None:  # type: ignore[no-untyped-def]
    assert [equity for _, equity in result.equity_curve] == EXPECTED_EQUITY


def test_ka2_final_equity(result) -> None:  # type: ignore[no-untyped-def]
    assert result.final_equity_cents == 9_996_270  # $99,962.70 exactly
    assert result.margin_breaches == []
