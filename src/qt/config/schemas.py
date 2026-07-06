"""Pydantic schemas for the four config files (BUILD_PLAN.md sections 1-3).

Design rules:
- ``extra="forbid"`` everywhere: a typoed key in a money-path config must be a
  startup failure, never a silently-ignored default.
- Cross-field invariants live in model validators so a bad combination
  (e.g. whitelisted symbol with no contract cap) can never load.
- Schemas describe *shape and sanity*, not policy: changing a risk limit is an
  owner edit to risk.yaml, not a code change.
"""

from __future__ import annotations

import math
import re
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# fullmatch everywhere: re.match + "$" tolerates a trailing newline ("MES\n" would pass).
SYMBOL_RE = re.compile(r"[A-Z0-9]{1,6}")

_TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

_GRID_MIN_DONCHIAN = 2
_TICK_TOLERANCE = 1e-9


class StrictModel(BaseModel):
    """Base for all config models: unknown keys are fatal."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_symbol(symbol: str) -> str:
    if not SYMBOL_RE.fullmatch(symbol):
        msg = f"invalid symbol {symbol!r}: must fully match {SYMBOL_RE.pattern}"
        raise ValueError(msg)
    return symbol


# ---------------------------------------------------------------------------
# risk.yaml
# ---------------------------------------------------------------------------


class RiskConfig(StrictModel):
    """Schema for config/risk.yaml (§2). The file itself is human-edited only."""

    mode: Literal["paper", "live"]
    # allow_inf_nan=False on every float: an `.inf` (or a "1e999" typo pydantic coerces
    # to inf) must never silently neutralize a risk limit.
    per_trade_risk_default: float = Field(gt=0.0, le=0.05, allow_inf_nan=False)
    per_trade_risk_max: float = Field(gt=0.0, le=0.05, allow_inf_nan=False)
    daily_loss_halt: float = Field(lt=0.0, ge=-1.0, allow_inf_nan=False)
    kill_drawdown_hwm: float = Field(lt=0.0, ge=-1.0, allow_inf_nan=False)
    gross_notional_max_x_equity: float = Field(gt=0.0, allow_inf_nan=False)
    max_contracts: dict[str, int]
    instrument_whitelist: list[str]
    price_collar_pct: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    mr_atr_gate_equity_pct: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    vix_max_for_mr: float = Field(gt=0.0, allow_inf_nan=False)
    event_blackout_min: int = Field(ge=0)
    rearm: Literal["manual"]  # v1: manual re-arm only (§2)

    @model_validator(mode="after")
    def _invariants(self) -> RiskConfig:
        if self.per_trade_risk_default > self.per_trade_risk_max:
            msg = (
                f"per_trade_risk_default ({self.per_trade_risk_default}) exceeds "
                f"per_trade_risk_max ({self.per_trade_risk_max})"
            )
            raise ValueError(msg)
        if self.kill_drawdown_hwm >= self.daily_loss_halt:
            msg = (
                f"kill_drawdown_hwm ({self.kill_drawdown_hwm}) must be strictly deeper "
                f"(more negative) than daily_loss_halt ({self.daily_loss_halt})"
            )
            raise ValueError(msg)
        for symbol in self.max_contracts:
            _check_symbol(symbol)
        seen: set[str] = set()
        for symbol in self.instrument_whitelist:
            _check_symbol(symbol)
            if symbol in seen:
                msg = f"duplicate symbol {symbol!r} in instrument_whitelist"
                raise ValueError(msg)
            seen.add(symbol)
            if symbol not in self.max_contracts:
                msg = f"whitelisted symbol {symbol!r} has no max_contracts entry"
                raise ValueError(msg)
            if self.max_contracts[symbol] <= 0:
                msg = (
                    f"whitelisted symbol {symbol!r} has max_contracts "
                    f"{self.max_contracts[symbol]} (must be > 0)"
                )
                raise ValueError(msg)
        for symbol, cap in self.max_contracts.items():
            if cap < 0:
                msg = f"max_contracts[{symbol!r}] is negative ({cap})"
                raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# instruments.yaml
# ---------------------------------------------------------------------------


class InstrumentSpec(StrictModel):
    """One futures contract's static spec + per-symbol cost constants."""

    name: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    currency: Literal["USD"]  # v1 is USD-only; widen deliberately, not accidentally
    dollars_per_point: float = Field(gt=0.0, allow_inf_nan=False)
    tick_size: float = Field(gt=0.0, allow_inf_nan=False)
    tick_value: float = Field(gt=0.0, allow_inf_nan=False)
    commission_per_side: float = Field(ge=0.0, allow_inf_nan=False)
    maintenance_margin: float = Field(gt=0.0, allow_inf_nan=False)  # $/contract, broker-set
    notes: str = ""

    @model_validator(mode="after")
    def _tick_consistency(self) -> InstrumentSpec:
        implied = self.dollars_per_point * self.tick_size
        if abs(implied - self.tick_value) > _TICK_TOLERANCE:
            msg = (
                f"tick_value {self.tick_value} inconsistent: dollars_per_point "
                f"({self.dollars_per_point}) x tick_size ({self.tick_size}) = {implied}"
            )
            raise ValueError(msg)
        return self


class SlippageConfig(StrictModel):
    """Session-aware baseline slippage (ticks/side) + mandatory stress multipliers."""

    rth_ticks_per_side: int = Field(ge=0)
    eth_ticks_per_side: int = Field(ge=0)
    stress_multipliers: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _invariants(self) -> SlippageConfig:
        if self.eth_ticks_per_side < self.rth_ticks_per_side:
            msg = (
                f"eth_ticks_per_side ({self.eth_ticks_per_side}) below rth_ticks_per_side "
                f"({self.rth_ticks_per_side}): overnight slippage cannot be better than RTH"
            )
            raise ValueError(msg)
        if any(m < 1 for m in self.stress_multipliers) or any(
            a >= b for a, b in pairwise(self.stress_multipliers)
        ):
            msg = (
                f"stress_multipliers must be strictly ascending and >= 1 "
                f"(no duplicates), got {self.stress_multipliers}"
            )
            raise ValueError(msg)
        required = {1, 2, 3}  # x1/x2/x3 stress runs are mandatory in validation (§1)
        if not required.issubset(set(self.stress_multipliers)):
            msg = f"stress_multipliers must include {sorted(required)}"
            raise ValueError(msg)
        return self


class InstrumentsConfig(StrictModel):
    """Schema for config/instruments.yaml."""

    instruments: dict[str, InstrumentSpec] = Field(min_length=1)
    slippage: SlippageConfig

    @model_validator(mode="after")
    def _symbols(self) -> InstrumentsConfig:
        for symbol in self.instruments:
            _check_symbol(symbol)
        return self


# ---------------------------------------------------------------------------
# strategies.yaml
# ---------------------------------------------------------------------------


class SessionWindow(StrictModel):
    """UTC entry window, "HH:MM" 24h. start == end is rejected; overnight spans allowed."""

    start: str
    end: str

    @model_validator(mode="after")
    def _valid_times(self) -> SessionWindow:
        for label, value in (("start", self.start), ("end", self.end)):
            if not _TIME_RE.fullmatch(value):
                msg = f"session {label} {value!r} is not HH:MM 24h UTC"
                raise ValueError(msg)
        if self.start == self.end:
            msg = f"session window start == end ({self.start!r}): empty or ambiguous window"
            raise ValueError(msg)
        return self


class TrendBreakoutParams(StrictModel):
    """One S1 configuration (TF-H or TF-D)."""

    enabled: bool
    symbols: list[str] = Field(min_length=1)
    bar_timeframe: Literal["1h", "1d"]
    donchian_n: int = Field(ge=2)
    atr_stop_k: float = Field(gt=0.0, allow_inf_nan=False)
    atr_period: int = Field(ge=2)
    entry_session_utc: SessionWindow | None = None
    allow_short: bool = True

    @model_validator(mode="after")
    def _symbols(self) -> TrendBreakoutParams:
        for symbol in self.symbols:
            _check_symbol(symbol)
        if len(set(self.symbols)) != len(self.symbols):
            msg = f"duplicate symbols in {self.symbols}"
            raise ValueError(msg)
        return self


class TrendResearchGrid(StrictModel):
    """Plateau-map grid (§3 S1). Changes only via the plateau rule."""

    donchian_n: list[int] = Field(min_length=2)
    atr_stop_k: list[float] = Field(min_length=2)

    @model_validator(mode="after")
    def _invariants(self) -> TrendResearchGrid:
        if any(n < _GRID_MIN_DONCHIAN for n in self.donchian_n) or any(
            a >= b for a, b in pairwise(self.donchian_n)
        ):
            msg = (
                f"donchian_n grid must be strictly ascending (no duplicates) and "
                f">= {_GRID_MIN_DONCHIAN}, got {self.donchian_n}"
            )
            raise ValueError(msg)
        if any(not math.isfinite(k) or k <= 0 for k in self.atr_stop_k) or any(
            a >= b for a, b in pairwise(self.atr_stop_k)
        ):
            msg = (
                f"atr_stop_k grid must be strictly ascending (no duplicates), finite, "
                f"and > 0, got {self.atr_stop_k}"
            )
            raise ValueError(msg)
        return self


class TrendBreakoutConfig(StrictModel):
    """S1 TREND_BREAKOUT: TF-H (deployment candidate) + TF-D (research) + grid."""

    tf_h: TrendBreakoutParams
    tf_d: TrendBreakoutParams
    research_grid: TrendResearchGrid

    @model_validator(mode="after")
    def _timeframes(self) -> TrendBreakoutConfig:
        if self.tf_h.bar_timeframe != "1h":
            msg = f"tf_h.bar_timeframe must be '1h', got {self.tf_h.bar_timeframe!r}"
            raise ValueError(msg)
        if self.tf_d.bar_timeframe != "1d":
            msg = f"tf_d.bar_timeframe must be '1d', got {self.tf_d.bar_timeframe!r}"
            raise ValueError(msg)
        if self.tf_h.entry_session_utc is None:
            msg = "tf_h requires entry_session_utc (entries restricted to liquid hours, §3)"
            raise ValueError(msg)
        return self


FillMode = Literal["same_close", "next_open"]


class MrRsi2Config(StrictModel):
    """S2 MR_RSI2 (§3). Long-only in v1; no scale-ins; hard stop never widened."""

    enabled: bool
    symbols: list[str] = Field(min_length=1)
    bar_timeframe: Literal["1d"]
    rsi_period: int = Field(ge=2)
    rsi_entry_below: float = Field(gt=0.0, lt=100.0, allow_inf_nan=False)
    rsi_exit_above: float = Field(gt=0.0, lt=100.0, allow_inf_nan=False)
    sma_filter_period: int = Field(ge=2)
    hard_stop_atr_mult: float = Field(gt=0.0, allow_inf_nan=False)
    hard_stop_atr_period: int = Field(ge=2)
    time_stop_bars: int = Field(ge=1)
    long_only: Literal[True]  # v1: long-only is a locked decision (§3)
    fill_modes: list[FillMode] = Field(min_length=2)

    @model_validator(mode="after")
    def _invariants(self) -> MrRsi2Config:
        for symbol in self.symbols:
            _check_symbol(symbol)
        if len(set(self.symbols)) != len(self.symbols):
            msg = f"duplicate symbols in {self.symbols}"
            raise ValueError(msg)
        if self.rsi_entry_below >= self.rsi_exit_above:
            msg = (
                f"rsi_entry_below ({self.rsi_entry_below}) must be strictly below "
                f"rsi_exit_above ({self.rsi_exit_above})"
            )
            raise ValueError(msg)
        if sorted(self.fill_modes) != ["next_open", "same_close"]:
            msg = (
                "fill_modes must contain exactly {'same_close', 'next_open'} once each: the "
                f"backtest reports BOTH and the worse governs (§3), got {self.fill_modes}"
            )
            raise ValueError(msg)
        return self


class StrategiesConfig(StrictModel):
    """Schema for config/strategies.yaml."""

    s1_trend_breakout: TrendBreakoutConfig
    s2_mr_rsi2: MrRsi2Config


# ---------------------------------------------------------------------------
# data.yaml
# ---------------------------------------------------------------------------


class IbkrPacing(StrictModel):
    """IBKR historical-data pacing limits (§1). Ceilings, not targets."""

    max_requests_per_10min: int = Field(ge=1, le=60)
    max_requests_per_2s_same_contract: int = Field(ge=1, le=6)


class IbkrDataConfig(StrictModel):
    history_years: int = Field(ge=1, le=2)  # IBKR hard limit: 2y past contract expiry
    pacing: IbkrPacing
    include_expired: bool


class RollConfig(StrictModel):
    """Roll-table rule + Panama adjustment (§1). Ratio adjustment is forbidden."""

    rule: Literal["volume"]
    volume_lookback_days: int = Field(ge=1)
    fallback_days_before_expiry: int = Field(ge=1)
    adjustment: Literal["panama"]


class DataPaths(StrictModel):
    raw_dir: str = Field(min_length=1)
    curated_dir: str = Field(min_length=1)
    calendar_file: str = Field(min_length=1)
    baseline_rtt_file: str = Field(min_length=1)

    @model_validator(mode="after")
    def _distinct(self) -> DataPaths:
        if self.raw_dir == self.curated_dir:
            msg = "raw_dir and curated_dir must differ (QC gates promotion raw -> curated)"
            raise ValueError(msg)
        return self


class VixSource(StrictModel):
    provider: Literal["cboe"]
    url: str = Field(pattern=r"^https://")


class DeepHistorySource(StrictModel):
    """Deep-history vendor. 'pending' = owner decision open (§6); Stooq results PROVISIONAL."""

    provider: Literal["pending", "databento", "firstrate"]
    provisional_fallback: Literal["stooq"]


class BinanceFundingSource(StrictModel):
    base_url: str = Field(pattern=r"^https://")
    symbol: str
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def _symbol(self) -> BinanceFundingSource:
        if not re.fullmatch(r"[A-Z0-9]{5,12}", self.symbol):
            msg = f"invalid Binance symbol {self.symbol!r}"
            raise ValueError(msg)
        return self


class DataSources(StrictModel):
    vix: VixSource
    deep_history: DeepHistorySource
    binance_funding: BinanceFundingSource


class QcConfig(StrictModel):
    outlier_sigma: float = Field(gt=0.0, allow_inf_nan=False)
    criticals_block_promotion: Literal[True]  # criticals always block promotion (§4.1)


class DataConfig(StrictModel):
    """Schema for config/data.yaml."""

    ibkr: IbkrDataConfig
    roll: RollConfig
    paths: DataPaths
    sources: DataSources
    qc: QcConfig


# ---------------------------------------------------------------------------
# Cross-file invariants
# ---------------------------------------------------------------------------


class AppConfig(StrictModel):
    """All four configs, cross-validated. Built by :func:`qt.config.loader.load_all_configs`."""

    risk: RiskConfig
    instruments: InstrumentsConfig
    strategies: StrategiesConfig
    data: DataConfig

    @model_validator(mode="after")
    def _cross_file(self) -> AppConfig:
        known = set(self.instruments.instruments)
        for symbol in self.risk.instrument_whitelist:
            if symbol not in known:
                msg = f"whitelisted symbol {symbol!r} missing from instruments.yaml"
                raise ValueError(msg)
        for symbol in self.risk.max_contracts:
            if symbol not in known:
                msg = f"max_contracts symbol {symbol!r} missing from instruments.yaml"
                raise ValueError(msg)
        strategy_symbols = (
            set(self.strategies.s1_trend_breakout.tf_h.symbols)
            | set(self.strategies.s1_trend_breakout.tf_d.symbols)
            | set(self.strategies.s2_mr_rsi2.symbols)
        )
        for symbol in strategy_symbols:
            if symbol not in known:
                msg = f"strategy symbol {symbol!r} missing from instruments.yaml"
                raise ValueError(msg)
            if symbol not in self.risk.max_contracts:
                msg = f"strategy symbol {symbol!r} has no max_contracts entry in risk.yaml"
                raise ValueError(msg)
        return self
