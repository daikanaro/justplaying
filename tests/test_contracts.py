"""Contract-calendar tests: expiries, symbols, chain construction."""

from datetime import date

import pytest

from qt.data.contracts import ContractMonth, contracts_covering, third_friday


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [
        (2024, 3, date(2024, 3, 15)),
        (2024, 6, date(2024, 6, 21)),
        (2024, 9, date(2024, 9, 20)),
        (2024, 12, date(2024, 12, 20)),
        (2025, 3, date(2025, 3, 21)),
        (2026, 6, date(2026, 6, 19)),
    ],
)
def test_third_friday(year: int, month: int, expected: date) -> None:
    assert third_friday(year, month) == expected


def test_contract_identity() -> None:
    c = ContractMonth(2024, 6, "MES")
    assert c.local_symbol == "MESM4"
    assert c.contract_id == "MESM2024"
    assert c.expiry == date(2024, 6, 21)


def test_non_quarterly_month_rejected() -> None:
    with pytest.raises(ValueError, match="not a quarterly month"):
        ContractMonth(2024, 5, "MES")


def test_next_quarterly_year_rollover() -> None:
    z = ContractMonth(2024, 12, "M2K")
    h = z.next_quarterly()
    assert (h.year, h.month, h.symbol) == (2025, 3, "M2K")


def test_contracts_covering_chain() -> None:
    chain = contracts_covering("MES", date(2024, 7, 1), date(2025, 7, 1))
    ids = [c.contract_id for c in chain]
    assert ids[0] == "MESU2024"  # first expiry >= start
    assert "MESM2025" in ids
    assert all(chain[i] < chain[i + 1] for i in range(len(chain) - 1))
    assert chain[-1].expiry >= date(2025, 7, 1)  # covers the live front past `end`


def test_contracts_covering_rejects_reversed_range() -> None:
    with pytest.raises(ValueError, match="before start"):
        contracts_covering("MES", date(2025, 1, 1), date(2024, 1, 1))
