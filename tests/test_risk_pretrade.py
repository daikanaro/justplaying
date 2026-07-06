"""Pre-trade choke-point tests: every §2 check, injected states."""

from pathlib import Path

import pytest

from qt.config import InstrumentsConfig, RiskConfig, load_config
from qt.risk.pretrade import ProposedOrder, RiskContext, pretrade_check

EQUITY = 10_000_000  # $100,000


@pytest.fixture(scope="module")
def risk(config_dir: Path) -> RiskConfig:
    return load_config(config_dir / "risk.yaml", RiskConfig)


@pytest.fixture(scope="module")
def instruments(config_dir: Path) -> InstrumentsConfig:
    return load_config(config_dir / "instruments.yaml", InstrumentsConfig)


def ctx(
    risk: RiskConfig,
    instruments: InstrumentsConfig,
    equity: int = EQUITY,
    positions: dict[str, int] | None = None,
    daily_halted: bool = False,
) -> RiskContext:
    return RiskContext(
        risk=risk,
        instruments=instruments,
        equity_cents=equity,
        positions=positions or {},
        last_marks={"MES": 5000.0, "M2K": 2000.0, "MNQ": 18000.0},
        daily_halted=daily_halted,
    )


def test_clean_entry_approved(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    verdict = pretrade_check(ProposedOrder("MES", 1, stop_price=4970.0), ctx(risk, instruments))
    assert verdict.approved
    assert verdict.reasons == []


def test_non_whitelisted_symbol_rejected(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    verdict = pretrade_check(ProposedOrder("MNQ", 1), ctx(risk, instruments))
    assert not verdict.approved
    assert any("not whitelisted" in r for r in verdict.reasons)
    assert any("exceeds cap 0" in r for r in verdict.reasons)


def test_per_symbol_cap_on_resulting_position(
    risk: RiskConfig, instruments: InstrumentsConfig
) -> None:
    # cap MES = 2: +3 from flat rejected; +1 on top of +2 rejected; +1 on +1 fine.
    assert not pretrade_check(ProposedOrder("MES", 3), ctx(risk, instruments)).approved
    held = ctx(risk, instruments, positions={"MES": 2})
    assert not pretrade_check(ProposedOrder("MES", 1), held).approved
    growing = ctx(risk, instruments, positions={"MES": 1})
    assert pretrade_check(ProposedOrder("MES", 1), growing).approved


def test_price_collar(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    # 1% collar around mark 5000: 5049 passes, 5051 rejected; stops checked too.
    context = ctx(risk, instruments)
    assert pretrade_check(ProposedOrder("MES", 1, price=5049.0), context).approved
    bad_price = pretrade_check(ProposedOrder("MES", 1, price=5051.0), context)
    assert not bad_price.approved
    bad_stop = pretrade_check(ProposedOrder("MES", 1, stop_price=4900.0), context)
    assert not bad_stop.approved  # >1% away AND fine for risk — collar still rejects


def test_gross_notional_cap(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    # 1 MES notional = 5000 x $5 = $25k; 3x equity on a $5k account = $15k -> reject.
    small = ctx(risk, instruments, equity=500_000)
    verdict = pretrade_check(ProposedOrder("MES", 1), small)
    assert not verdict.approved
    assert any("gross notional" in r for r in verdict.reasons)
    # Existing positions count: MES 1 held (~$25k) + M2K 6 (~$60k) vs $100k x3.
    held = ctx(risk, instruments, positions={"MES": 1})
    assert pretrade_check(ProposedOrder("M2K", 6), held).approved


def test_per_trade_risk_cap(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    # Budget = 1% of $100k = $1,000. 2 MES with a 45-pt stop = $450 -> fine;
    # 2 MES with a 40-pt stop is fine, but a 2 x 110-pt stop = $1,100 -> reject
    # (collar-compatible: 110/5000 = 2.2% would ALSO trip the collar, so use
    # a 45-pt stop for the pass case and quantity to push risk over budget).
    context = ctx(risk, instruments)
    ok = pretrade_check(ProposedOrder("MES", 2, stop_price=4955.0), context)
    assert ok.approved  # 45 pts x 2 x $5 = $450
    too_risky = pretrade_check(ProposedOrder("M2K", 6, stop_price=1962.0), context)
    # 38 pts x 6 x $5 = $1,140 > $1,000, and 38/2000 = 1.9%... collar trips too;
    # assert specifically on the risk reason:
    assert any("per-trade risk" in r for r in too_risky.reasons)


def test_daily_halt_blocks_entries_allows_exits(
    risk: RiskConfig, instruments: InstrumentsConfig
) -> None:
    halted = ctx(risk, instruments, positions={"MES": 2}, daily_halted=True)
    exit_order = pretrade_check(ProposedOrder("MES", -2), halted)
    assert exit_order.approved  # reduce to flat: allowed (§2: exits still allowed)
    partial_exit = pretrade_check(ProposedOrder("MES", -1), halted)
    assert partial_exit.approved
    flip = pretrade_check(ProposedOrder("MES", -3), halted)
    assert not flip.approved  # crossing flat opens a NEW position
    fresh_entry = pretrade_check(ProposedOrder("M2K", 1), halted)
    assert not fresh_entry.approved


def test_zero_quantity_and_missing_mark(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    assert not pretrade_check(ProposedOrder("MES", 0), ctx(risk, instruments)).approved
    no_mark = RiskContext(
        risk=risk,
        instruments=instruments,
        equity_cents=EQUITY,
        positions={},
        last_marks={},
    )
    verdict = pretrade_check(ProposedOrder("MES", 1), no_mark)
    assert not verdict.approved
    assert any("no last mark" in r for r in verdict.reasons)


def test_all_failures_reported_together(risk: RiskConfig, instruments: InstrumentsConfig) -> None:
    halted = ctx(risk, instruments, equity=500_000, daily_halted=True)
    verdict = pretrade_check(ProposedOrder("MNQ", 5, price=20000.0), halted)
    joined = " | ".join(verdict.reasons)
    assert "not whitelisted" in joined
    assert "daily loss halt" in joined
    assert "exceeds cap" in joined
    assert "from last mark" in joined  # collar: 20000 vs mark 18000
    assert "gross notional" in joined
