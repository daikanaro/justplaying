"""Shared fixtures for production-strategy tests: compact configs and
hand-controllable bar builders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from qt.backtest.events import Bar
from qt.config.schemas import (
    InstrumentsConfig,
    InstrumentSpec,
    MrRsi2Config,
    RiskConfig,
    SessionWindow,
    SlippageConfig,
    TrendBreakoutParams,
)

TICK = 0.25
SPECS = {"TST": (5.0, TICK)}


def risk_config(max_contracts: int = 5) -> RiskConfig:
    return RiskConfig(
        mode="paper",
        per_trade_risk_default=0.005,
        per_trade_risk_max=0.01,
        daily_loss_halt=-0.03,
        kill_drawdown_hwm=-0.35,
        gross_notional_max_x_equity=3.0,
        max_contracts={"TST": max_contracts},
        instrument_whitelist=["TST"] if max_contracts > 0 else [],
        price_collar_pct=0.01,
        mr_atr_gate_equity_pct=0.025,
        vix_max_for_mr=35,
        event_blackout_min=30,
        rearm="manual",
    )


def s1_params(
    donchian_n: int = 5,
    atr_period: int = 5,
    allow_short: bool = True,
    window: tuple[str, str] | None = ("13:30", "21:00"),
) -> TrendBreakoutParams:
    return TrendBreakoutParams(
        enabled=True,
        symbols=["TST"],
        bar_timeframe="1h",
        donchian_n=donchian_n,
        atr_stop_k=3.0,
        atr_period=atr_period,
        entry_session_utc=SessionWindow(start=window[0], end=window[1]) if window else None,
        allow_short=allow_short,
    )


def s2_params(time_stop_bars: int = 5, rsi_entry: float = 60.0) -> MrRsi2Config:
    return MrRsi2Config(
        enabled=True,
        symbols=["TST"],
        bar_timeframe="1d",
        rsi_period=2,
        rsi_entry_below=rsi_entry,  # loose test threshold; production value pinned by config tests
        rsi_exit_above=65.0,
        sma_filter_period=5,
        hard_stop_atr_mult=2.5,
        hard_stop_atr_period=3,
        time_stop_bars=time_stop_bars,
        long_only=True,
        fill_modes=["same_close", "next_open"],
    )


def make_instruments() -> InstrumentsConfig:
    return InstrumentsConfig(
        instruments={
            "TST": InstrumentSpec(
                name="Test Micro",
                exchange="CME",
                currency="USD",
                dollars_per_point=5.0,
                tick_size=TICK,
                tick_value=1.25,
                commission_per_side=0.80,
                maintenance_margin=1000.0,
            )
        },
        slippage=SlippageConfig(
            rth_ticks_per_side=1, eth_ticks_per_side=2, stress_multipliers=[1, 2, 3]
        ),
    )


def align(price: float) -> float:
    return round(price / TICK) * TICK


def hourly_bars(
    closes: list[float],
    start: datetime = datetime(2024, 7, 8, 14, 0, tzinfo=UTC),  # Monday, inside the window
    spread: float = 1.0,
) -> list[Bar]:
    bars = []
    for i, raw in enumerate(closes):
        close = align(raw)
        opn = align(closes[i - 1]) if i else close
        bars.append(
            Bar(
                ts=start + timedelta(hours=i),
                open=opn,
                high=max(opn, close) + spread,
                low=min(opn, close) - spread,
                close=close,
                volume=100.0,
            )
        )
    return bars


def daily_bars(
    closes: list[float],
    start: datetime = datetime(2024, 7, 1, 21, 0, tzinfo=UTC),
    spread: float = 1.0,
) -> list[Bar]:
    bars = []
    for i, raw in enumerate(closes):
        close = align(raw)
        opn = align(closes[i - 1]) if i else close
        bars.append(
            Bar(
                ts=start + timedelta(days=i),
                open=opn,
                high=max(opn, close) + spread,
                low=min(opn, close) - spread,
                close=close,
                volume=100.0,
            )
        )
    return bars
