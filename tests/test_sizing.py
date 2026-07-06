"""§1 sizing rules — hand-computed cases, including the rounding edge the
plan calls out explicitly (never round 0 -> 1)."""

import pytest

from qt.strategies.sizing import contracts_for_risk, size_position, vol_target_cap

EQUITY = 10_000_000  # $100,000


def test_core_formula_hand_case() -> None:
    # f=0.005 -> $500 budget; stop 10 pts x $5/pt = $50/contract -> exactly 10.
    assert contracts_for_risk(EQUITY, 0.005, 10.0, 5.0) == 10


def test_fraction_below_half_is_zero_never_one() -> None:
    # $500 budget; stop 250 pts x $5/pt = $1,250/contract -> fractional 0.4 -> 0.
    assert contracts_for_risk(EQUITY, 0.005, 250.0, 5.0) == 0


def test_round_half_up_not_bankers() -> None:
    # fractional exactly 0.5 -> 1 (the plan's boundary), 1.5 -> 2, 2.5 -> 3.
    assert contracts_for_risk(EQUITY, 0.005, 100.0, 10.0) == 1  # 500/1000 = 0.5
    assert contracts_for_risk(EQUITY, 0.005, 200.0 / 3.0, 5.0) == 2  # 500/333.33 = 1.5
    assert contracts_for_risk(EQUITY, 0.005, 20.0, 10.0) == 3  # 500/200 = 2.5


def test_zero_or_negative_equity_is_zero() -> None:
    assert contracts_for_risk(0, 0.005, 10.0, 5.0) == 0
    assert contracts_for_risk(-100, 0.005, 10.0, 5.0) == 0


def test_input_validation() -> None:
    with pytest.raises(ValueError, match="risk_fraction"):
        contracts_for_risk(EQUITY, 0.0, 10.0, 5.0)
    with pytest.raises(ValueError, match="must be > 0"):
        contracts_for_risk(EQUITY, 0.005, 0.0, 5.0)
    with pytest.raises(ValueError, match="daily_dollar_vol"):
        vol_target_cap(EQUITY, 0.0)
    with pytest.raises(ValueError, match="max_contracts"):
        size_position(EQUITY, 0.005, 10.0, 5.0, 100.0, -1)


def test_vol_target_cap_hand_case() -> None:
    # Daily budget = $100,000 * 0.20 / sqrt(252) = $1,259.88...;
    # $100/contract/day -> floor(12.59) = 12.
    assert vol_target_cap(EQUITY, 100.0) == 12
    # $2,000/contract/day -> floor(0.63) = 0: the overlay can force zero.
    assert vol_target_cap(EQUITY, 2000.0) == 0


def test_size_position_takes_the_binding_constraint() -> None:
    # risk formula says 10, vol cap says 12, max_contracts says 2 -> 2.
    assert size_position(EQUITY, 0.005, 10.0, 5.0, 100.0, 2) == 2
    # vol cap binds: risk 10, vol 3 (415-ish $/contract), cap 6 -> 3.
    assert size_position(EQUITY, 0.005, 10.0, 5.0, 400.0, 6) == 3
    # whitelist-excluded symbol: max_contracts 0 -> always 0.
    assert size_position(EQUITY, 0.005, 10.0, 5.0, 100.0, 0) == 0
