"""Indicator tests against HAND-COMPUTED fixtures (§3: hand-rolled,
unit-tested against hand-computed fixtures)."""

import pytest

from qt.indicators import atr, donchian_high, donchian_low, ema, rsi, sma, true_range

CLOSES = [10.0, 11.0, 12.0, 11.0, 10.0, 9.0, 10.0, 12.0]


def test_sma_hand_computed() -> None:
    out = sma(CLOSES, 3)
    assert out[0] is None and out[1] is None
    assert out[2] == pytest.approx(11.0)  # (10+11+12)/3
    assert out[3] == pytest.approx(34 / 3)  # (11+12+11)/3
    assert out[7] == pytest.approx(31 / 3)  # (9+10+12)/3


def test_ema_hand_computed() -> None:
    # period 3 -> alpha = 0.5, seeded with SMA(first 3) = 11.
    out = ema(CLOSES, 3)
    assert out[1] is None
    assert out[2] == pytest.approx(11.0)
    assert out[3] == pytest.approx(11.0)  # 11 + 0.5*(11-11)
    assert out[4] == pytest.approx(10.5)  # 11 + 0.5*(10-11)
    assert out[5] == pytest.approx(9.75)  # 10.5 + 0.5*(9-10.5)


def test_true_range_hand_computed() -> None:
    highs = [12.0, 13.0, 15.0]
    lows = [10.0, 11.0, 14.0]
    closes = [11.0, 12.0, 14.5]
    # TR0 = 12-10 = 2; TR1 = max(2, |13-11|, |11-11|) = 2;
    # TR2 = max(1, |15-12|, |14-12|) = 3 (gap up dominates).
    assert true_range(highs, lows, closes) == [2.0, 2.0, 3.0]


def test_atr_wilder_hand_computed() -> None:
    highs = [12.0, 13.0, 15.0, 16.0]
    lows = [10.0, 11.0, 14.0, 15.0]
    closes = [11.0, 12.0, 14.5, 15.5]
    # TRs = [2, 2, 3, max(1, |16-14.5|, |15-14.5|) = 1.5]
    # ATR(2): seed at i=1 = (2+2)/2 = 2; i=2 = (2*1+3)/2 = 2.5; i=3 = (2.5+1.5)/2 = 2.
    out = atr(highs, lows, closes, 2)
    assert out[0] is None
    assert out[1] == pytest.approx(2.0)
    assert out[2] == pytest.approx(2.5)
    assert out[3] == pytest.approx(2.0)


def test_rsi_wilder_hand_computed() -> None:
    closes = [10.0, 11.0, 10.5, 11.5, 12.0]
    # period 2: changes = [+1, -0.5, +1, +0.5]
    # seed (i=2): avg_gain = (1+0)/2 = 0.5, avg_loss = (0+0.5)/2 = 0.25
    #   RS = 2 -> RSI = 100 - 100/3 = 66.666...
    # i=3: gain (0.5*1+1)/2 = 0.75, loss (0.25*1+0)/2 = 0.125 -> RS=6 -> RSI = 600/7 = 85.714...
    # i=4: gain (0.75+0.5)/2 = 0.625, loss 0.0625 -> RS=10 -> RSI = 1000/11 = 90.909...
    out = rsi(closes, 2)
    assert out[1] is None
    assert out[2] == pytest.approx(100 * 2 / 3)
    assert out[3] == pytest.approx(600 / 7)
    assert out[4] == pytest.approx(1000 / 11)


def test_rsi_all_gains_and_flat() -> None:
    assert rsi([1.0, 2.0, 3.0, 4.0], 2)[3] == 100.0
    assert rsi([5.0, 5.0, 5.0, 5.0], 2)[3] == 50.0  # flat is neutral, not overbought


def test_donchian_excludes_current_bar() -> None:
    highs = [10.0, 12.0, 11.0, 15.0, 9.0]
    out = donchian_high(highs, 3)
    assert out[0] is None and out[2] is None
    assert out[3] == pytest.approx(12.0)  # max of bars 0..2, NOT the 15 printed now
    assert out[4] == pytest.approx(15.0)  # max of bars 1..3


def test_donchian_low_excludes_current_bar() -> None:
    lows = [10.0, 8.0, 9.0, 5.0, 11.0]
    out = donchian_low(lows, 3)
    assert out[3] == pytest.approx(8.0)  # min of bars 0..2, NOT today's 5
    assert out[4] == pytest.approx(5.0)


def test_insufficient_data_is_all_none() -> None:
    assert sma([1.0, 2.0], 5) == [None, None]
    assert ema([1.0, 2.0], 5) == [None, None]
    assert rsi([1.0, 2.0], 5) == [None, None]


def test_bad_period_rejected() -> None:
    with pytest.raises(ValueError, match="period"):
        sma([1.0], 0)


def test_mismatched_lengths_rejected() -> None:
    with pytest.raises(ValueError, match="length"):
        true_range([1.0], [1.0, 2.0], [1.0])
