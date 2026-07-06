"""THE cost model (BUILD_PLAN §1 constants, §4 requirement).

This is the single implementation used by the backtester and, from slice 4.5,
the live executor. Both import from here; forking it is forbidden (CLAUDE.md).

All money amounts are integer cents — portfolio accounting is exact to the
cent (§4), so costs must be too. Slippage is session-aware (1 tick/side RTH,
2 ticks/side overnight) with a stress multiplier hook (x1/x2/x3 mandatory in
validation). Constants are config-driven and recalibrated from real paper
fills in slice 4.7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qt.config.schemas import InstrumentsConfig
from qt.data.sessions import is_rth

_CENT_TOLERANCE = 1e-6


def dollars_to_cents(amount: float) -> int:
    """Exact-cent conversion; rejects amounts that are not whole cents."""
    cents = round(amount * 100)
    if abs(amount * 100 - cents) > _CENT_TOLERANCE:
        msg = f"amount {amount} is not a whole number of cents"
        raise ValueError(msg)
    return cents


@dataclass(frozen=True)
class InstrumentCosts:
    tick_size: float
    tick_value_cents: int
    commission_per_side_cents: int
    dollars_per_point: float
    maintenance_margin_cents: int


class CostModel:
    """Commission + session-aware slippage per §1, in integer cents."""

    def __init__(self, config: InstrumentsConfig, stress_multiplier: int = 1) -> None:
        if stress_multiplier < 1:
            msg = f"stress_multiplier must be >= 1, got {stress_multiplier}"
            raise ValueError(msg)
        self._stress = stress_multiplier
        self._rth_ticks = config.slippage.rth_ticks_per_side
        self._eth_ticks = config.slippage.eth_ticks_per_side
        self._instruments = {
            symbol: InstrumentCosts(
                tick_size=spec.tick_size,
                tick_value_cents=dollars_to_cents(spec.tick_value),
                commission_per_side_cents=dollars_to_cents(spec.commission_per_side),
                dollars_per_point=spec.dollars_per_point,
                maintenance_margin_cents=dollars_to_cents(spec.maintenance_margin),
            )
            for symbol, spec in config.instruments.items()
        }

    def spec(self, symbol: str) -> InstrumentCosts:
        try:
            return self._instruments[symbol]
        except KeyError:
            msg = f"no cost spec for symbol {symbol!r}"
            raise KeyError(msg) from None

    def commission_cents(self, symbol: str, contracts: int) -> int:
        """Commission for one side (entry OR exit) of ``contracts`` contracts."""
        if contracts < 0:
            msg = f"contracts must be >= 0, got {contracts}"
            raise ValueError(msg)
        return self.spec(symbol).commission_per_side_cents * contracts

    def slippage_ticks(self, ts_utc: datetime) -> int:
        """Adverse ticks per side for market/stop orders at this instant."""
        base = self._rth_ticks if is_rth(ts_utc) else self._eth_ticks
        return base * self._stress

    def slippage_ticks_rth(self) -> int:
        """Configured RTH baseline (unstressed) — for recalibration reports."""
        return self._rth_ticks

    def slippage_ticks_eth(self) -> int:
        """Configured ETH baseline (unstressed) — for recalibration reports."""
        return self._eth_ticks

    def slippage_points(self, symbol: str, ts_utc: datetime) -> float:
        return self.slippage_ticks(ts_utc) * self.spec(symbol).tick_size

    def price_to_ticks(self, symbol: str, price: float) -> int:
        """Absolute price as an integer tick count. Engine prices must be
        tick-aligned; anything else is an upstream bug and raises."""
        spec = self.spec(symbol)
        ticks = round(price / spec.tick_size)
        if abs(price - ticks * spec.tick_size) > spec.tick_size * 1e-6:
            msg = f"{symbol}: price {price} is not tick-aligned (tick {spec.tick_size})"
            raise ValueError(msg)
        return ticks

    def points_to_cents(self, symbol: str, points: float) -> int:
        """Exact $-cents for a price difference, via tick counting.

        ``points`` must be a whole number of ticks (all engine fills are
        tick-aligned); anything else is an upstream bug and raises.
        """
        spec = self.spec(symbol)
        ticks = round(points / spec.tick_size)
        if abs(points - ticks * spec.tick_size) > spec.tick_size * 1e-6:
            msg = f"{symbol}: {points} points is not a whole number of ticks"
            raise ValueError(msg)
        return ticks * spec.tick_value_cents

    def funding_accrual_cents(self, symbol: str, ts_utc: datetime) -> int:
        """Funding hook — present but inert for venue 1 (§4). Venue 2 wires this."""
        return 0
