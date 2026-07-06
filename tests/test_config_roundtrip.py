"""The four shipped config files load, validate, and round-trip losslessly."""

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from qt.config import (
    AppConfig,
    DataConfig,
    InstrumentsConfig,
    RiskConfig,
    StrategiesConfig,
    load_all_configs,
    load_config,
)

FILES: list[tuple[str, type[BaseModel]]] = [
    ("risk.yaml", RiskConfig),
    ("instruments.yaml", InstrumentsConfig),
    ("strategies.yaml", StrategiesConfig),
    ("data.yaml", DataConfig),
]


@pytest.mark.parametrize(("filename", "model"), FILES)
def test_shipped_config_loads(config_dir: Path, filename: str, model: type[BaseModel]) -> None:
    cfg = load_config(config_dir / filename, model)
    assert isinstance(cfg, model)


@pytest.mark.parametrize(("filename", "model"), FILES)
def test_roundtrip_dump_revalidate(config_dir: Path, filename: str, model: type[BaseModel]) -> None:
    cfg = load_config(config_dir / filename, model)
    dumped = cfg.model_dump()
    revalidated = model.model_validate(dumped)
    assert revalidated == cfg
    assert revalidated.model_dump() == dumped


@pytest.mark.parametrize(("filename", "model"), FILES)
def test_roundtrip_through_yaml(
    tmp_path: Path, config_dir: Path, filename: str, model: type[BaseModel]
) -> None:
    cfg = load_config(config_dir / filename, model)
    rewritten = tmp_path / filename
    rewritten.write_text(yaml.safe_dump(cfg.model_dump()), encoding="utf-8")
    assert load_config(rewritten, model) == cfg


def test_all_configs_cross_validate(config_dir: Path) -> None:
    app = load_all_configs(config_dir)
    assert isinstance(app, AppConfig)


def test_shipped_risk_values_match_plan(config_dir: Path) -> None:
    """§2 initial risk.yaml values, pinned so a drive-by edit is loud. Owner edits are
    legitimate — when they happen, this test is updated deliberately alongside them."""
    risk = load_config(config_dir / "risk.yaml", RiskConfig)
    assert risk.mode == "paper"
    assert risk.per_trade_risk_default == 0.005
    assert risk.per_trade_risk_max == 0.01
    assert risk.daily_loss_halt == -0.03
    assert risk.kill_drawdown_hwm == -0.35
    assert risk.gross_notional_max_x_equity == 3.0
    assert risk.max_contracts == {"MES": 2, "M2K": 6, "MNQ": 0}
    assert risk.instrument_whitelist == ["MES", "M2K"]
    assert risk.price_collar_pct == 0.01
    assert risk.mr_atr_gate_equity_pct == 0.025
    assert risk.vix_max_for_mr == 35
    assert risk.event_blackout_min == 30
    assert risk.rearm == "manual"


def test_shipped_instrument_specs_match_plan(config_dir: Path) -> None:
    """§1 instrument table: $/point, tick, tick $."""
    cfg = load_config(config_dir / "instruments.yaml", InstrumentsConfig)
    assert set(cfg.instruments) == {"MES", "M2K", "MNQ"}
    mes, m2k, mnq = cfg.instruments["MES"], cfg.instruments["M2K"], cfg.instruments["MNQ"]
    assert (mes.dollars_per_point, mes.tick_size, mes.tick_value) == (5.0, 0.25, 1.25)
    assert (m2k.dollars_per_point, m2k.tick_size, m2k.tick_value) == (5.0, 0.10, 0.50)
    assert (mnq.dollars_per_point, mnq.tick_size, mnq.tick_value) == (2.0, 0.25, 0.50)
    assert all(spec.commission_per_side == 0.80 for spec in cfg.instruments.values())
    assert cfg.slippage.rth_ticks_per_side == 1
    assert cfg.slippage.eth_ticks_per_side == 2
    assert cfg.slippage.stress_multipliers == [1, 2, 3]
