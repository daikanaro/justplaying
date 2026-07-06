"""Cost-model tests: the single implementation both engines will share."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qt.config import InstrumentsConfig, load_config
from qt.costs.model import CostModel, dollars_to_cents

RTH_TS = datetime(2024, 7, 8, 15, 0, tzinfo=UTC)  # Monday 10:00 CT
ETH_TS = datetime(2024, 7, 8, 2, 0, tzinfo=UTC)  # overnight


@pytest.fixture(scope="module")
def costs(config_dir: Path) -> CostModel:
    return CostModel(load_config(config_dir / "instruments.yaml", InstrumentsConfig))


def test_dollars_to_cents_exact() -> None:
    assert dollars_to_cents(0.80) == 80
    assert dollars_to_cents(1.25) == 125
    with pytest.raises(ValueError, match="whole number of cents"):
        dollars_to_cents(0.001)


def test_commission(costs: CostModel) -> None:
    assert costs.commission_cents("MES", 2) == 160
    assert costs.commission_cents("MES", 0) == 0
    with pytest.raises(ValueError, match=">= 0"):
        costs.commission_cents("MES", -1)
    with pytest.raises(KeyError, match="ZZZ"):
        costs.commission_cents("ZZZ", 1)


def test_slippage_session_aware(costs: CostModel) -> None:
    assert costs.slippage_ticks(RTH_TS) == 1
    assert costs.slippage_ticks(ETH_TS) == 2
    assert costs.slippage_points("MES", RTH_TS) == pytest.approx(0.25)
    assert costs.slippage_points("M2K", ETH_TS) == pytest.approx(0.20)


def test_stress_multiplier(config_dir: Path) -> None:
    config = load_config(config_dir / "instruments.yaml", InstrumentsConfig)
    stressed = CostModel(config, stress_multiplier=3)
    assert stressed.slippage_ticks(RTH_TS) == 3
    assert stressed.slippage_ticks(ETH_TS) == 6
    with pytest.raises(ValueError, match="stress_multiplier"):
        CostModel(config, stress_multiplier=0)


def test_points_to_cents_exact(costs: CostModel) -> None:
    assert costs.points_to_cents("MES", 1.0) == 500  # 4 ticks x $1.25
    assert costs.points_to_cents("MES", -7.5) == -3750  # KA-2 trade-1 loss per contract
    assert costs.points_to_cents("M2K", 0.1) == 50
    with pytest.raises(ValueError, match="whole number of ticks"):
        costs.points_to_cents("MES", 0.30)


def test_price_to_ticks(costs: CostModel) -> None:
    assert costs.price_to_ticks("MES", 5000.25) == 20001
    assert costs.price_to_ticks("M2K", 2000.30) == 20003
    with pytest.raises(ValueError, match="tick-aligned"):
        costs.price_to_ticks("MES", 5000.10)


def test_funding_hook_inert(costs: CostModel) -> None:
    assert costs.funding_accrual_cents("MES", RTH_TS) == 0
