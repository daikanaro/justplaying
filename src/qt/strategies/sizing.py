"""Position sizing per BUILD_PLAN §1 (locked decision, both strategies).

    N = round( f * equity / (k_stop * ATR * $per_point) )
    - if fractional N < 0.5 -> trade 0. NEVER round 0 -> 1.
    - volatility-target overlay: position daily $vol <= (0.20/sqrt(252)) * equity.
    - per-symbol max_contracts cap from risk.yaml applies last.

"round" here is round-half-up on the positive fraction (0.5 -> 1, 1.5 -> 2),
implemented explicitly — Python's banker's rounding would turn 1.5 into 2 but
2.5 into 2, which is not what the plan says.
"""

from __future__ import annotations

import math

ANNUAL_VOL_TARGET = 0.20
TRADING_DAYS_PER_YEAR = 252.0
_HALF = 0.5


def contracts_for_risk(
    equity_cents: int,
    risk_fraction: float,
    stop_points: float,
    dollars_per_point: float,
) -> int:
    """§1 core formula. ``stop_points`` is the stop distance (k_stop * ATR)."""
    if equity_cents <= 0:
        return 0
    if not 0.0 < risk_fraction < 1.0:
        msg = f"risk_fraction must be in (0, 1), got {risk_fraction}"
        raise ValueError(msg)
    if stop_points <= 0.0 or dollars_per_point <= 0.0:
        msg = f"stop_points ({stop_points}) and $/point ({dollars_per_point}) must be > 0"
        raise ValueError(msg)
    risk_cents_per_contract = stop_points * dollars_per_point * 100.0
    fractional = (risk_fraction * equity_cents) / risk_cents_per_contract
    if fractional < _HALF:
        return 0  # never round 0 -> 1
    return math.floor(fractional + _HALF)  # round half up


def vol_target_cap(equity_cents: int, daily_dollar_vol_per_contract: float) -> int:
    """Max contracts so position daily $vol <= (0.20/sqrt(252)) * equity."""
    if equity_cents <= 0:
        return 0
    if daily_dollar_vol_per_contract <= 0.0:
        msg = f"daily_dollar_vol_per_contract must be > 0, got {daily_dollar_vol_per_contract}"
        raise ValueError(msg)
    daily_budget_cents = equity_cents * ANNUAL_VOL_TARGET / math.sqrt(TRADING_DAYS_PER_YEAR)
    return math.floor(daily_budget_cents / (daily_dollar_vol_per_contract * 100.0))


def size_position(  # noqa: PLR0913 - the §1 formula has exactly these inputs
    equity_cents: int,
    risk_fraction: float,
    stop_points: float,
    dollars_per_point: float,
    daily_dollar_vol_per_contract: float,
    max_contracts: int,
) -> int:
    """Full §1 sizing: risk formula, then vol-target overlay, then the
    per-symbol cap from risk.yaml. Any layer can force 0."""
    if max_contracts < 0:
        msg = f"max_contracts must be >= 0, got {max_contracts}"
        raise ValueError(msg)
    by_risk = contracts_for_risk(equity_cents, risk_fraction, stop_points, dollars_per_point)
    by_vol = vol_target_cap(equity_cents, daily_dollar_vol_per_contract)
    return max(0, min(by_risk, by_vol, max_contracts))
