"""Independent watchdog (§2 semantics, §4.6 acceptance).

Runs as its OWN process (scripts/watchdog.py), never inside the engine: a
frozen engine cannot silence its own watchdog. Each tick it derives equity
from injected providers (journal + broker) and enforces:

- daily_loss_halt: day P&L <= threshold -> new entries blocked for the rest of
  the session (exits still allowed). Communicated via a daily-halt flag file
  that the pre-trade choke point reads; expires automatically on session roll.
- kill_drawdown_hwm: drawdown from the high-water mark <= threshold ->
  cancel-all, flatten (reduce-only), write the HALT flag, alert. All within
  the SAME tick. The engine refuses to start while HALT exists; re-arm is the
  owner deleting the file (never code).

State (HWM, session date, day-start equity) persists to a JSON file so a
watchdog restart cannot forget the high-water mark.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from qt.config.schemas import RiskConfig
from qt.oms.alerts import Alerter
from qt.oms.halt import write_halt


class BrokerActions(Protocol):
    """The two emergency actions the watchdog may take, provided by the OMS."""

    def cancel_all(self) -> None: ...
    def flatten_all(self) -> None: ...  # reduce-only market exits


class WatchdogAction(StrEnum):
    NONE = "none"
    DAILY_HALT = "daily_halt"
    KILL = "kill"


@dataclass(frozen=True)
class WatchdogConfig:
    state_path: Path
    daily_halt_flag: Path
    halt_flag: Path


@dataclass
class _State:
    hwm_cents: int
    session_date: str  # ISO date of the current session
    day_start_equity_cents: int
    daily_halted: bool

    @classmethod
    def load(cls, path: Path, equity_cents: int, today: date) -> _State:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                hwm_cents=int(raw["hwm_cents"]),
                session_date=str(raw["session_date"]),
                day_start_equity_cents=int(raw["day_start_equity_cents"]),
                daily_halted=bool(raw["daily_halted"]),
            )
        return cls(
            hwm_cents=equity_cents,
            session_date=today.isoformat(),
            day_start_equity_cents=equity_cents,
            daily_halted=False,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "hwm_cents": self.hwm_cents,
                    "session_date": self.session_date,
                    "day_start_equity_cents": self.day_start_equity_cents,
                    "daily_halted": self.daily_halted,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


class Watchdog:
    def __init__(
        self,
        risk: RiskConfig,
        config: WatchdogConfig,
        broker: BrokerActions,
        alerter: Alerter,
    ) -> None:
        self._risk = risk
        self._config = config
        self._broker = broker
        self._alerter = alerter

    def tick(self, equity_cents: int, today: date) -> WatchdogAction:
        """One watchdog cycle. The kill path completes inside this call —
        that is the §4.6 acceptance ('within one watchdog cycle')."""
        state = _State.load(self._config.state_path, equity_cents, today)

        if state.session_date != today.isoformat():  # session roll
            state.session_date = today.isoformat()
            state.day_start_equity_cents = equity_cents
            if state.daily_halted:
                state.daily_halted = False
                self._config.daily_halt_flag.unlink(missing_ok=True)

        state.hwm_cents = max(state.hwm_cents, equity_cents)
        action = WatchdogAction.NONE

        drawdown = (equity_cents - state.hwm_cents) / state.hwm_cents
        if drawdown <= self._risk.kill_drawdown_hwm:
            reason = (
                f"KILL: drawdown {drawdown:.2%} from HWM breaches "
                f"{self._risk.kill_drawdown_hwm:.2%} (equity {equity_cents / 100:.2f}, "
                f"HWM {state.hwm_cents / 100:.2f})"
            )
            self._broker.cancel_all()
            self._broker.flatten_all()
            write_halt(self._config.halt_flag, reason)
            self._alerter.alert(reason)
            action = WatchdogAction.KILL
        else:
            day_pnl = (
                (equity_cents - state.day_start_equity_cents) / state.day_start_equity_cents
                if state.day_start_equity_cents > 0
                else 0.0
            )
            if day_pnl <= self._risk.daily_loss_halt and not state.daily_halted:
                state.daily_halted = True
                reason = (
                    f"DAILY HALT: day P&L {day_pnl:.2%} breaches "
                    f"{self._risk.daily_loss_halt:.2%}; new entries blocked until next session"
                )
                self._config.daily_halt_flag.parent.mkdir(parents=True, exist_ok=True)
                self._config.daily_halt_flag.write_text(reason + "\n", encoding="utf-8")
                self._alerter.alert(reason)
                action = WatchdogAction.DAILY_HALT

        state.save(self._config.state_path)
        return action

    def daily_halted(self) -> bool:
        """What the pre-trade choke point consults (RiskContext.daily_halted)."""
        return self._config.daily_halt_flag.exists()
