"""Watchdog tests — the §4.6 acceptance drills at unit level: injected -3%
day halts new entries; injected -35% drawdown executes the full kill within
ONE tick and the engine refuses restart until the flag is cleared."""

import json
from datetime import date
from pathlib import Path

import pytest

from qt.config import RiskConfig, load_config
from qt.oms.alerts import LogAlerter
from qt.oms.halt import HaltError, require_not_halted
from qt.risk.watchdog import Watchdog, WatchdogAction, WatchdogConfig

D0 = date(2026, 7, 6)
D1 = date(2026, 7, 7)
START = 10_000_000  # $100,000


class FakeBroker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def cancel_all(self) -> None:
        self.calls.append("cancel_all")

    def flatten_all(self) -> None:
        self.calls.append("flatten_all")


@pytest.fixture
def setup(
    tmp_path: Path, config_dir: Path
) -> tuple[Watchdog, FakeBroker, LogAlerter, WatchdogConfig]:
    risk = load_config(config_dir / "risk.yaml", RiskConfig)
    config = WatchdogConfig(
        state_path=tmp_path / "watchdog_state.json",
        daily_halt_flag=tmp_path / "DAILY_HALT",
        halt_flag=tmp_path / "HALT",
    )
    broker = FakeBroker()
    alerter = LogAlerter()
    return Watchdog(risk, config, broker, alerter), broker, alerter, config


def test_quiet_day_no_action(setup) -> None:  # type: ignore[no-untyped-def]
    watchdog, broker, alerter, _config = setup
    assert watchdog.tick(START, D0) is WatchdogAction.NONE
    assert watchdog.tick(START - 100_000, D0) is WatchdogAction.NONE  # -1%: fine
    assert broker.calls == []
    assert alerter.messages == []
    assert not watchdog.daily_halted()


def test_injected_minus_3pct_day_halts_new_entries(setup) -> None:  # type: ignore[no-untyped-def]
    watchdog, broker, alerter, config = setup
    watchdog.tick(START, D0)
    action = watchdog.tick(9_650_000, D0)  # -3.5% on the day
    assert action is WatchdogAction.DAILY_HALT
    assert watchdog.daily_halted()  # the pre-trade choke point reads this
    assert config.daily_halt_flag.exists()
    assert len(alerter.messages) == 1
    assert broker.calls == []  # halt is entries-only: no cancel, no flatten
    # Further ticks the same day: no repeat alert, still halted.
    assert watchdog.tick(9_600_000, D0) is WatchdogAction.NONE
    assert len(alerter.messages) == 1


def test_daily_halt_expires_on_session_roll(setup) -> None:  # type: ignore[no-untyped-def]
    watchdog, _broker, _alerter, config = setup
    watchdog.tick(START, D0)
    watchdog.tick(9_650_000, D0)
    assert watchdog.daily_halted()
    watchdog.tick(9_650_000, D1)  # new session: day-start resets to current equity
    assert not watchdog.daily_halted()
    assert not config.daily_halt_flag.exists()


def test_injected_minus_35pct_kills_within_one_tick(setup) -> None:  # type: ignore[no-untyped-def]
    watchdog, broker, alerter, config = setup
    watchdog.tick(START, D0)
    action = watchdog.tick(6_400_000, D0)  # -36% from HWM
    assert action is WatchdogAction.KILL
    # The FULL kill inside the single tick: cancel-all, flatten, HALT, alert.
    assert broker.calls == ["cancel_all", "flatten_all"]
    assert config.halt_flag.exists()
    assert len(alerter.messages) == 1
    # Engine refuses restart until the OWNER clears the flag.
    with pytest.raises(HaltError, match="refuses to start"):
        require_not_halted(config.halt_flag)
    config.halt_flag.unlink()  # the owner's manual re-arm
    require_not_halted(config.halt_flag)  # now clean


def test_hwm_ratchets_and_survives_restart(setup, tmp_path: Path, config_dir: Path) -> None:  # type: ignore[no-untyped-def]
    watchdog, broker, _alerter, config = setup
    watchdog.tick(START, D0)
    watchdog.tick(12_000_000, D0)  # new HWM $120k
    state = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert state["hwm_cents"] == 12_000_000

    # A NEW watchdog process against the same state file keeps the HWM:
    risk = load_config(config_dir / "risk.yaml", RiskConfig)
    reborn = Watchdog(risk, config, broker, LogAlerter())
    # $120k -> $7.7M... rather: 7,700,000 cents = $77k = -35.8% from $120k HWM.
    assert reborn.tick(7_700_000, D1) is WatchdogAction.KILL


def test_kill_takes_priority_over_daily_halt(setup) -> None:  # type: ignore[no-untyped-def]
    watchdog, _broker, _alerter, config = setup
    watchdog.tick(START, D0)
    action = watchdog.tick(6_000_000, D0)  # -40%: breaches BOTH thresholds
    assert action is WatchdogAction.KILL
    assert not config.daily_halt_flag.exists()  # kill supersedes; no half measures
