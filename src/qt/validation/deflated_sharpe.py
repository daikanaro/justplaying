"""Deflated Sharpe ratio (Bailey & Lopez de Prado 2014).

DSR answers: given that N strategy variants were tried (the TRUE trial count
from the experiment log), what is the probability that the best observed
Sharpe is real rather than selection bias?

    PSR(SR*) = Phi[ (SR - SR*) * sqrt(n - 1) / sqrt(1 - g3*SR + (g4-1)/4 * SR^2) ]
    DSR      = PSR(SR0),  SR0 = sqrt(V[SR]) * [(1-g)*PhiInv(1 - 1/N) + g*PhiInv(1 - 1/(N*e))]

where g is the Euler-Mascheroni constant, g3 skewness, g4 kurtosis (normal=3),
n the number of returns, and V[SR] the variance of Sharpe estimates across the
N trials. All SRs are per-period (NOT annualized).

No scipy: Phi uses math.erf; PhiInv is Acklam's rational approximation
(|relative error| < 1.2e-9), unit-tested against known quantiles.
"""

from __future__ import annotations

import math

EULER_GAMMA = 0.5772156649015329

# Acklam's inverse-normal-CDF coefficients.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW = 0.02425
_MIN_OBS = 2
_MIN_TRIALS = 2


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam). Domain: 0 < p < 1."""
    if not 0.0 < p < 1.0:
        msg = f"normal_ppf domain is (0, 1), got {p}"
        raise ValueError(msg)
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    if p > 1.0 - _P_LOW:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return ((((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q) / (
        ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
    )


def probabilistic_sharpe(
    sharpe: float, benchmark: float, n_obs: int, skew: float = 0.0, kurtosis: float = 3.0
) -> float:
    """PSR: probability the true SR exceeds ``benchmark`` given the estimate."""
    if n_obs < _MIN_OBS:
        msg = f"PSR needs at least 2 observations, got {n_obs}"
        raise ValueError(msg)
    variance_term = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if variance_term <= 0.0:
        msg = f"degenerate SR variance term {variance_term} (skew {skew}, kurtosis {kurtosis})"
        raise ValueError(msg)
    z = (sharpe - benchmark) * math.sqrt(n_obs - 1.0) / math.sqrt(variance_term)
    return normal_cdf(z)


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """E[max SR] under N independent zero-skill trials with variance V[SR]."""
    if n_trials < _MIN_TRIALS:
        msg = f"deflation needs at least 2 trials, got {n_trials}"
        raise ValueError(msg)
    if sr_variance < 0.0:
        msg = f"sr_variance must be >= 0, got {sr_variance}"
        raise ValueError(msg)
    z1 = normal_ppf(1.0 - 1.0 / n_trials)
    z2 = normal_ppf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(sr_variance) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)


def deflated_sharpe(
    sharpe: float,
    n_obs: int,
    n_trials: int,
    sr_variance: float,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """DSR: PSR against the expected-max-SR benchmark from ``n_trials`` tries."""
    benchmark = expected_max_sharpe(n_trials, sr_variance)
    return probabilistic_sharpe(sharpe, benchmark, n_obs, skew, kurtosis)
