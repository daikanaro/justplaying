"""Heartbeat + dead-man tests — the frozen-process drill at unit level:
the alert fires in under 60 seconds of a stall, exactly once per stall."""

from pathlib import Path

import pytest

from qt.oms.alerts import LogAlerter
from qt.risk.heartbeat import DEFAULT_MAX_AGE_S, DeadManSwitch, beat


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_default_threshold_fires_under_60s() -> None:
    assert DEFAULT_MAX_AGE_S < 60.0


def test_fresh_heartbeat_passes(tmp_path: Path) -> None:
    clock = FakeClock()
    path = tmp_path / "engine.heartbeat"
    alerter = LogAlerter()
    switch = DeadManSwitch(path, alerter, clock=clock)
    beat(path, clock)
    clock.now += 10.0
    assert switch.check()
    assert alerter.messages == []


def test_stale_heartbeat_fires_once_then_rearms(tmp_path: Path) -> None:
    clock = FakeClock()
    path = tmp_path / "engine.heartbeat"
    alerter = LogAlerter()
    switch = DeadManSwitch(path, alerter, clock=clock)
    beat(path, clock)
    clock.now += DEFAULT_MAX_AGE_S + 1.0  # frozen past the threshold
    assert not switch.check()
    assert len(alerter.messages) == 1
    assert "DEAD-MAN" in alerter.messages[0]
    assert not switch.check()  # still frozen: no alert spam
    assert len(alerter.messages) == 1
    beat(path, clock)  # process thawed
    assert switch.check()
    clock.now += DEFAULT_MAX_AGE_S + 1.0  # frozen AGAIN: new stall, new alert
    assert not switch.check()
    assert len(alerter.messages) == 2


def test_missing_heartbeat_file_fires(tmp_path: Path) -> None:
    alerter = LogAlerter()
    switch = DeadManSwitch(tmp_path / "never_written.heartbeat", alerter)
    assert not switch.check()
    assert len(alerter.messages) == 1
    assert "missing" in alerter.messages[0]


def test_corrupt_heartbeat_treated_as_missing(tmp_path: Path) -> None:
    path = tmp_path / "engine.heartbeat"
    path.write_text("not a timestamp\n", encoding="utf-8")
    alerter = LogAlerter()
    assert not DeadManSwitch(path, alerter).check()
    assert len(alerter.messages) == 1


def test_bad_threshold_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_age_s"):
        DeadManSwitch(tmp_path / "x", LogAlerter(), max_age_s=0.0)
