"""Roll-rule tests: volume crossover, expiry fallback, chain sequencing."""

from datetime import date, timedelta

import polars as pl
import pytest

from qt.data.contracts import ContractMonth
from qt.data.roll_table import Roll, RollTableError, build_roll_table, roll_table_frame

MESH24 = ContractMonth(2024, 3, "MES")  # expiry 2024-03-15
MESM24 = ContractMonth(2024, 6, "MES")  # expiry 2024-06-21


def weekdays(start: date, end: date) -> list[date]:
    out, day = [], start
    while day <= end:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def volume_frame(days: list[date], volumes: list[int]) -> pl.DataFrame:
    return pl.DataFrame({"date": days, "volume": volumes}).with_columns(
        pl.col("date").cast(pl.Date)
    )


def test_volume_crossover_sets_roll_date() -> None:
    days = weekdays(date(2024, 2, 1), date(2024, 3, 14))
    front = volume_frame(days, [1000] * len(days))
    # Next contract wakes up on 2024-03-05: 2000/day. 5-day rolling sums cross
    # on the third heavy day, 2024-03-07 (2000*3 + 100*2 = 6200 > 5000).
    next_vols = [100 if d < date(2024, 3, 5) else 2000 for d in days]
    nxt = volume_frame(days, next_vols)
    rolls = build_roll_table(
        [MESH24, MESM24],
        {MESH24.contract_id: front, MESM24.contract_id: nxt},
    )
    assert rolls == [Roll(date(2024, 3, 7), "MESH2024", "MESM2024")]


def test_fallback_five_business_days_before_expiry() -> None:
    days = weekdays(date(2024, 2, 1), date(2024, 3, 14))
    front = volume_frame(days, [1000] * len(days))
    nxt = volume_frame(days, [1] * len(days))  # never crosses
    rolls = build_roll_table(
        [MESH24, MESM24],
        {MESH24.contract_id: front, MESM24.contract_id: nxt},
    )
    # Expiry Fri 2024-03-15; 5 business days back -> Fri 2024-03-08.
    assert rolls == [Roll(date(2024, 3, 8), "MESH2024", "MESM2024")]


def test_missing_volume_data_raises() -> None:
    days = weekdays(date(2024, 2, 1), date(2024, 3, 14))
    front = volume_frame(days, [1000] * len(days))
    with pytest.raises(RollTableError, match="MESM2024"):
        build_roll_table([MESH24, MESM24], {MESH24.contract_id: front})


def test_unordered_contracts_rejected() -> None:
    days = weekdays(date(2024, 2, 1), date(2024, 3, 14))
    vols = {c.contract_id: volume_frame(days, [1] * len(days)) for c in (MESH24, MESM24)}
    with pytest.raises(RollTableError, match="ordered by expiry"):
        build_roll_table([MESM24, MESH24], vols)


def test_single_contract_needs_no_roll() -> None:
    assert build_roll_table([MESH24], {}) == []


def test_three_contract_chain_rolls_are_strictly_ordered() -> None:
    mesu = ContractMonth(2024, 9, "MES")  # expiry 2024-09-20
    days = weekdays(date(2024, 2, 1), date(2024, 9, 19))
    always = volume_frame(days, [1] * len(days))
    rolls = build_roll_table(
        [MESH24, MESM24, mesu],
        {
            MESH24.contract_id: volume_frame(days, [1000] * len(days)),
            MESM24.contract_id: always,
            mesu.contract_id: always,
        },
    )
    assert len(rolls) == 2
    assert rolls[0].date < rolls[1].date
    assert rolls[0].to_contract == rolls[1].from_contract


def test_roll_table_frame_roundtrip() -> None:
    rolls = [Roll(date(2024, 3, 7), "MESH2024", "MESM2024")]
    frame = roll_table_frame(rolls)
    assert frame.height == 1
    assert frame.get_column("from_contract").to_list() == ["MESH2024"]
