"""Panama stitcher acceptance tests (slice 4.1 gate):
(a) point differences preserved across rolls,
(b) no unexplained roll-day jump (the splice-day move equals the incoming
    contract's own move, never the calendar-spread basis).
"""

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import polars as pl
import pytest

from qt.data.panama import RollAdjustment, StitchError, stitch_panama
from qt.data.roll_table import Roll


def daily_bars(start: date, closes: list[float], volume: int = 1000) -> pl.DataFrame:
    ts = [
        datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i)
        for i in range(len(closes))
    ]
    return pl.DataFrame(
        {
            "ts": ts,
            "open": [c - 0.5 for c in closes],
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
            "volume": [float(volume)] * len(closes),
        }
    ).with_columns(pl.col("ts").dt.replace_time_zone("UTC"))


START = date(2024, 3, 4)  # Monday
ROLL_DATE = date(2024, 3, 6)  # Wednesday, third bar

# Contract A trades 100..104; contract B trades at a +5..+6 premium.
BARS_A = daily_bars(START, [100.0, 101.0, 102.0, 103.0, 104.0])
BARS_B = daily_bars(START, [105.0, 106.5, 107.0, 109.0, 110.0])
ONE_ROLL = [Roll(ROLL_DATE, "A", "B")]


def stitched() -> tuple[pl.DataFrame, list[RollAdjustment]]:
    return stitch_panama({"A": BARS_A, "B": BARS_B}, ONE_ROLL)


def test_offset_is_basis_at_roll_close() -> None:
    _, audit = stitched()
    assert audit == [RollAdjustment(ROLL_DATE, "A", "B", 5.0)]  # 107 - 102


def test_newest_segment_unadjusted() -> None:
    continuous, _ = stitched()
    tail = continuous.tail(2)
    assert tail.get_column("close").to_list() == [109.0, 110.0]  # raw B prices
    assert tail.get_column("adjustment").to_list() == [0.0, 0.0]
    assert set(tail.get_column("contract").to_list()) == {"B"}


def test_point_differences_preserved_within_segments() -> None:
    continuous, _ = stitched()
    adjusted_a = continuous.filter(pl.col("contract") == "A").get_column("close").to_list()
    raw_a = [100.0, 101.0, 102.0]
    assert [b - a for a, b in pairwise(adjusted_a)] == [b - a for a, b in pairwise(raw_a)]


def test_no_unexplained_roll_day_jump() -> None:
    """The close-to-close move across the splice must equal contract B's OWN
    move over those bars (109 - 107 = 2) — not the naive concat jump
    (109 - 102 = 7), which would embed the +5 basis into P&L."""
    continuous, _ = stitched()
    closes = continuous.sort("ts").get_column("close").to_list()
    moves = [b - a for a, b in pairwise(closes)]
    assert moves == [1.0, 1.0, 2.0, 1.0]
    assert closes == [105.0, 106.0, 107.0, 109.0, 110.0]


def test_all_price_columns_shifted_equally() -> None:
    continuous, _ = stitched()
    first = continuous.sort("ts").head(1)
    # Raw A bar 1: open 99.5, high 101, low 99, close 100; +5 across the board.
    assert first.get_column("open")[0] == pytest.approx(104.5)
    assert first.get_column("high")[0] == pytest.approx(106.0)
    assert first.get_column("low")[0] == pytest.approx(104.0)
    assert first.get_column("close")[0] == pytest.approx(105.0)


def test_two_rolls_cumulative_adjustment() -> None:
    bars_c = daily_bars(START, [103.0, 104.5, 105.0, 107.0, 108.0, 109.5, 111.0][:5])
    second_roll = Roll(date(2024, 3, 7), "B", "C")
    continuous, audit = stitch_panama(
        {"A": BARS_A, "B": BARS_B, "C": bars_c},
        [Roll(ROLL_DATE, "A", "B"), second_roll],
    )
    # Offset B->C at 2024-03-07 (4th bar): C 107 - B 109 = -2.
    assert [a.offset for a in audit] == [5.0, -2.0]
    oldest = continuous.sort("ts").head(1)
    assert oldest.get_column("adjustment")[0] == pytest.approx(3.0)  # 5 + (-2)
    assert oldest.get_column("close")[0] == pytest.approx(103.0)  # 100 + 3
    # Still no unexplained jumps anywhere.
    closes = continuous.sort("ts").get_column("close").to_list()
    moves = [b - a for a, b in pairwise(closes)]
    assert moves == [1.0, 1.0, 2.0, 1.0]  # A(+1,+1) | B move +2 | C move +1


def test_hourly_bars_splice_at_session_boundary() -> None:
    hours_a = pl.DataFrame(
        {
            "ts": [
                datetime(2024, 3, 6, 14, 0, tzinfo=UTC),
                datetime(2024, 3, 6, 15, 0, tzinfo=UTC),
                datetime(2024, 3, 7, 14, 0, tzinfo=UTC),
            ],
            "open": [99.5, 100.5, 101.5],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.0, 101.0, 102.0],
            "volume": [1.0, 1.0, 1.0],
        }
    ).with_columns(pl.col("ts").dt.replace_time_zone("UTC"))
    hours_b = hours_a.with_columns(
        *[(pl.col(c) + 4.0).alias(c) for c in ("open", "high", "low", "close")]
    )
    continuous, audit = stitch_panama(
        {"A": hours_a, "B": hours_b}, [Roll(date(2024, 3, 6), "A", "B")]
    )
    # Offset from the LAST common bar on the roll date (15:00): 105 - 101 = 4.
    assert audit[0].offset == pytest.approx(4.0)
    assert continuous.height == 3
    # A bars on the roll date, B bars after; nothing duplicated.
    assert continuous.get_column("contract").to_list() == ["A", "A", "B"]
    assert continuous.get_column("close").to_list() == [104.0, 105.0, 106.0]


def test_missing_contract_bars_rejected() -> None:
    with pytest.raises(StitchError, match="no bars were provided"):
        stitch_panama({"A": BARS_A}, ONE_ROLL)


def test_no_common_bar_on_roll_date_rejected() -> None:
    disjoint_b = daily_bars(date(2024, 3, 11), [107.0, 108.0])  # starts after the roll
    with pytest.raises(StitchError, match="share no bar"):
        stitch_panama({"A": BARS_A, "B": disjoint_b}, ONE_ROLL)


def test_empty_roll_list_rejected() -> None:
    with pytest.raises(StitchError, match="at least one roll"):
        stitch_panama({"A": BARS_A}, [])
