"""Heartbeat files + dead-man alert (§4.6).

The engine (and any other watched process) calls ``beat`` on every loop
iteration; the watchdog calls ``check`` each tick. A stale or missing
heartbeat fires the dead-man alert — once per stall, not once per tick.
The acceptance drill requires the alert to fire in under 60 seconds; the
default threshold leaves margin for one slow watchdog cycle.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from qt.oms.alerts import Alerter

DEFAULT_MAX_AGE_S = 45.0  # < 60s acceptance with a full watchdog cycle to spare


def beat(path: Path, clock: Callable[[], float] = time.time) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{clock():.3f}\n", encoding="utf-8")


class DeadManSwitch:
    def __init__(
        self,
        heartbeat_path: Path,
        alerter: Alerter,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_age_s <= 0:
            msg = f"max_age_s must be > 0, got {max_age_s}"
            raise ValueError(msg)
        self._path = heartbeat_path
        self._alerter = alerter
        self._max_age_s = max_age_s
        self._clock = clock
        self._tripped = False

    def check(self) -> bool:
        """True if the heartbeat is fresh. Fires the dead-man alert on the
        FIRST stale observation; re-arms automatically once beats resume."""
        age = self._age()
        if age is not None and age <= self._max_age_s:
            self._tripped = False
            return True
        if not self._tripped:
            self._tripped = True
            detail = "missing" if age is None else f"stale by {age:.1f}s"
            self._alerter.alert(
                f"DEAD-MAN: heartbeat {self._path} is {detail} "
                f"(threshold {self._max_age_s:.0f}s) — watched process presumed frozen"
            )
        return False

    def _age(self) -> float | None:
        try:
            written = float(self._path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return self._clock() - written
