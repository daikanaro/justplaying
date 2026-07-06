"""Deflated Sharpe tests, including the §4.3-acceptance hand-computed case.

The hand computation below was derived INDEPENDENTLY of the implementation:
Phi-inverse values via bisection on the erf-based normal CDF (200 iterations),
then the Bailey & Lopez de Prado formulas evaluated step by step.
"""

import pytest

from qt.validation.deflated_sharpe import (
    deflated_sharpe,
    expected_max_sharpe,
    normal_cdf,
    normal_ppf,
    probabilistic_sharpe,
)


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.5, 0.0),
        (0.9, 1.281552),
        (0.975, 1.959964),
        (0.9632121, 1.789242),  # 1 - 1/(10e), used by the hand case below
        (0.025, -1.959964),
        (0.0001, -3.719016),
    ],
)
def test_normal_ppf_known_quantiles(p: float, expected: float) -> None:
    assert normal_ppf(p) == pytest.approx(expected, abs=1e-5)


def test_normal_cdf_ppf_inverse() -> None:
    for p in (0.001, 0.1, 0.5, 0.77, 0.999):
        assert normal_cdf(normal_ppf(p)) == pytest.approx(p, abs=1e-9)


def test_normal_ppf_domain() -> None:
    for bad in (0.0, 1.0, -0.5, 2.0):
        with pytest.raises(ValueError, match="domain"):
            normal_ppf(bad)


def test_deflated_sharpe_matches_hand_computation() -> None:
    """Hand case: SR = 0.35 over n = 253 observations, normal returns
    (skew 0, kurtosis 3), N = 10 trials with V[SR] = 0.04.

    Step by step (bisection-derived quantiles):
      z1 = PhiInv(1 - 1/10)      = PhiInv(0.9)       = 1.281552
      z2 = PhiInv(1 - 1/(10e))   = PhiInv(0.9632121) = 1.789242
      SR0 = sqrt(0.04) * [(1-0.577216)*1.281552 + 0.577216*1.789242] = 0.314920
      denom = sqrt(1 - 0*SR + ((3-1)/4)*0.35^2) = sqrt(1.06125) = 1.030170
      z = (0.35 - 0.314920) * sqrt(252) / 1.030170 = 0.540574
      DSR = Phi(0.540574) = 0.705599
    """
    assert expected_max_sharpe(10, 0.04) == pytest.approx(0.314920, abs=1e-5)
    dsr = deflated_sharpe(sharpe=0.35, n_obs=253, n_trials=10, sr_variance=0.04)
    assert dsr == pytest.approx(0.705599, abs=1e-4)


def test_more_trials_deflate_harder() -> None:
    few = deflated_sharpe(sharpe=0.35, n_obs=253, n_trials=5, sr_variance=0.04)
    many = deflated_sharpe(sharpe=0.35, n_obs=253, n_trials=500, sr_variance=0.04)
    assert many < few  # the TRUE trial count matters: more tries, less credibility


def test_psr_against_zero_benchmark() -> None:
    # A solidly positive SR over a year of dailies: PSR(0) near 1.
    assert probabilistic_sharpe(0.35, 0.0, 253) > 0.999
    # SR equal to the benchmark: exactly 0.5.
    assert probabilistic_sharpe(0.2, 0.2, 253) == pytest.approx(0.5)


def test_negative_skew_reduces_psr() -> None:
    symmetric = probabilistic_sharpe(0.3, 0.1, 253, skew=0.0)
    left_tailed = probabilistic_sharpe(0.3, 0.1, 253, skew=-1.5)
    assert left_tailed < symmetric


def test_input_validation() -> None:
    with pytest.raises(ValueError, match="at least 2 observations"):
        probabilistic_sharpe(0.3, 0.0, 1)
    with pytest.raises(ValueError, match="at least 2 trials"):
        expected_max_sharpe(1, 0.04)
    with pytest.raises(ValueError, match="sr_variance"):
        expected_max_sharpe(10, -0.1)
