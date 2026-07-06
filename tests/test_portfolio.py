"""Portfolio accounting tests: FIFO lots, exact cents, invariant, margin."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.backtest.events import FillEvent
from qt.backtest.portfolio import AccountingError, Portfolio
from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel

TS = datetime(2024, 7, 8, 15, 0, tzinfo=UTC)
CASH = 10_000_000  # $100,000.00


@pytest.fixture
def portfolio(config_dir: Path) -> Portfolio:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    return Portfolio(costs, CASH)


def fill(symbol: str, quantity: int, price: float, commission: int = 0) -> FillEvent:
    return FillEvent(
        ts=TS,
        symbol=symbol,
        quantity=quantity,
        price=price,
        commission_cents=commission,
        reason="test",
    )


def test_open_and_mark(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("MES", 2, 5000.00, commission=160))
    assert portfolio.cash_cents == CASH - 160
    assert portfolio.equity_cents == CASH - 160  # unrealized 0 at entry
    portfolio.mark_to_market(TS, {"MES": 5001.00})  # +4 ticks x 125c x 2
    assert portfolio.equity_cents == CASH - 160 + 1000
    assert portfolio.cash_cents == CASH - 160  # marks never touch cash


def test_full_close_realizes(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("MES", 2, 5000.00))
    portfolio.apply_fill(fill("MES", -2, 5002.50))  # +10 ticks x 125 x 2 = 2500
    assert portfolio.cash_cents == CASH + 2500
    assert portfolio.equity_cents == CASH + 2500
    assert portfolio.quantity("MES") == 0


def test_partial_close_fifo(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("MES", 1, 5000.00))
    portfolio.apply_fill(fill("MES", 1, 5001.00))
    portfolio.apply_fill(fill("MES", -1, 5003.00))  # closes the 5000 lot: +12 ticks = 1500c
    assert portfolio.cash_cents == CASH + 1500
    assert portfolio.quantity("MES") == 1
    # Remaining lot entered at 5001, marked at 5003: +8 ticks = 1000c unrealized.
    assert portfolio.equity_cents == CASH + 1500 + 1000


def test_flip_long_to_short(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("MES", 1, 5000.00))
    portfolio.apply_fill(fill("MES", -3, 4999.00))  # close +1 (-500c), open -2 @ 4999
    assert portfolio.quantity("MES") == -2
    assert portfolio.cash_cents == CASH - 500
    portfolio.mark_to_market(TS, {"MES": 4998.00})  # shorts gain 4 ticks x 125 x 2 = 1000
    assert portfolio.equity_cents == CASH - 500 + 1000


def test_short_loss_math(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("M2K", -6, 2000.00))
    portfolio.apply_fill(fill("M2K", 6, 2001.50))  # -15 ticks x 50c x 6 = -4500
    assert portfolio.cash_cents == CASH - 4500


def test_invariant_catches_tampering(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("MES", 1, 5000.00))
    portfolio.equity_cents += 1  # corrupt the incremental figure
    with pytest.raises(AccountingError, match="invariant"):
        portfolio.check_invariant(TS)


def test_non_tick_aligned_fill_rejected(portfolio: Portfolio) -> None:
    with pytest.raises(ValueError, match="tick-aligned"):
        portfolio.apply_fill(fill("MES", 1, 5000.10))


def test_zero_quantity_fill_rejected(portfolio: Portfolio) -> None:
    with pytest.raises(AccountingError, match="zero-quantity"):
        portfolio.apply_fill(fill("MES", 0, 5000.00))


def test_margin_breach_recorded(config_dir: Path) -> None:
    costs = CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))
    small = Portfolio(costs, 300_000)  # $3,000
    small.apply_fill(fill("MES", 2, 5000.00))  # maintenance 2 x $2,400 = $4,800 > $3,000
    small.check_margin(TS)
    assert small.margin_breaches == [TS]
    assert Portfolio(costs, CASH).margin_breaches == []


def test_funding_hook_noop(portfolio: Portfolio) -> None:
    portfolio.apply_fill(fill("MES", 1, 5000.00))
    before = portfolio.equity_cents
    portfolio.accrue_funding(TS)
    assert portfolio.equity_cents == before
