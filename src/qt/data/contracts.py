"""Quarterly futures contract identities for CME equity index micros.

MES/M2K/MNQ trade the Mar/Jun/Sep/Dec cycle; trading terminates the third
Friday of the contract month (9:30 ET, cash-settled). Tick values live in
config/instruments.yaml — this module only knows the calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

QUARTERLY_MONTHS = (3, 6, 9, 12)
MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset = (4 - first.weekday()) % 7  # 4 = Friday
    return first + timedelta(days=offset + 14)


@dataclass(frozen=True, order=True)
class ContractMonth:
    """One listed quarterly contract, ordered by (year, month)."""

    year: int
    month: int
    symbol: str

    def __post_init__(self) -> None:
        if self.month not in QUARTERLY_MONTHS:
            msg = f"{self.symbol} {self.year}-{self.month}: not a quarterly month"
            raise ValueError(msg)

    @property
    def expiry(self) -> date:
        """Last trade date (third Friday of the contract month)."""
        return third_friday(self.year, self.month)

    @property
    def local_symbol(self) -> str:
        """IBKR localSymbol, e.g. MESM4 for MES June 2024."""
        return f"{self.symbol}{MONTH_CODES[self.month]}{self.year % 10}"

    @property
    def contract_id(self) -> str:
        """Unambiguous id used in filenames and roll tables, e.g. MESM2024."""
        return f"{self.symbol}{MONTH_CODES[self.month]}{self.year}"

    def next_quarterly(self) -> ContractMonth:
        idx = QUARTERLY_MONTHS.index(self.month)
        if idx == len(QUARTERLY_MONTHS) - 1:
            return ContractMonth(self.year + 1, QUARTERLY_MONTHS[0], self.symbol)
        return ContractMonth(self.year, QUARTERLY_MONTHS[idx + 1], self.symbol)


def contracts_covering(symbol: str, start: date, end: date) -> list[ContractMonth]:
    """Quarterly contracts whose expiry falls in [start, end + one quarter],
    ordered by expiry — the set a continuous series over [start, end] needs
    (including the still-active front at ``end``)."""
    if end < start:
        msg = f"end {end} before start {start}"
        raise ValueError(msg)
    out: list[ContractMonth] = []
    # First quarterly whose expiry is not before `start`.
    candidate = ContractMonth(start.year, QUARTERLY_MONTHS[0], symbol)
    while candidate.expiry < start:
        candidate = candidate.next_quarterly()
    horizon = end + timedelta(days=100)  # one quarter past `end` covers the live front
    while candidate.expiry <= horizon:
        out.append(candidate)
        candidate = candidate.next_quarterly()
    return out
