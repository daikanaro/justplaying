"""Monte Carlo trade-order reshuffle tests."""

import pytest

from qt.validation.mc_reshuffle import max_drawdown_cents, reshuffle_drawdowns


def test_max_drawdown_hand_case() -> None:
    # Equity path: 5, 3, 6, 1, 4 -> peak 6, trough 1 -> drawdown -5.
    assert max_drawdown_cents([5, -2, 3, -5, 3]) == -5
    assert max_drawdown_cents([1, 1, 1]) == 0
    assert max_drawdown_cents([-3, -4]) == -7


def test_reshuffle_is_deterministic_and_ordered() -> None:
    trades = [500, -300, 800, -900, 200, -100, 400, -250] * 4
    a = reshuffle_drawdowns(trades, n_paths=500, seed=42)
    b = reshuffle_drawdowns(trades, n_paths=500, seed=42)
    assert a == b  # seeded: fully reproducible
    # Deep tail is at least as bad as the median, which is at least as bad as p05.
    assert a.drawdown_worst_cents <= a.drawdown_p95_cents <= a.drawdown_p50_cents
    assert a.drawdown_p50_cents <= a.drawdown_p05_cents <= 0
    assert 0.0 <= a.observed_percentile <= 1.0
    assert a.n_paths == 500


def test_reshuffle_contains_observed_ordering_effects() -> None:
    """All losses first = the worst possible ordering: the observed drawdown
    is deeper than almost every reshuffle, so the fraction of paths at or
    deeper than it (observed_percentile) must be tiny — that reading is
    exactly how the memo will flag 'this equity curve got lucky/unlucky'."""
    trades = [-1000] * 10 + [1000] * 10
    result = reshuffle_drawdowns(trades, n_paths=2000, seed=7)
    assert result.observed_max_drawdown_cents == -10_000
    assert result.observed_percentile < 0.05
    assert result.drawdown_worst_cents >= -10_000  # nothing can be deeper


def test_reshuffle_requires_trades() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        reshuffle_drawdowns([100], n_paths=10)
