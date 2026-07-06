"""Risk engine + monitoring (BUILD_PLAN slice 4.6).

- qt.risk.pretrade — the SINGLE pre-trade choke point (§4.6): every order
  passes through pretrade_check or it does not go out.
- qt.risk.watchdog — independent process logic enforcing §2 semantics:
  daily_loss_halt blocks new entries (exits allowed); kill_drawdown_hwm
  cancels all, flattens, writes HALT, alerts; re-arm is manual.
- qt.risk.heartbeat — heartbeat files + dead-man alert.
- qt.risk.telegram — Telegram alerter (token is an owner item, outside the
  repo); alert failures degrade to logging, never into the money path.
- qt.risk.nightly — journal vs broker-statement reconciliation.
"""

from qt.risk.pretrade import ProposedOrder, RiskContext, Verdict, pretrade_check
from qt.risk.watchdog import Watchdog, WatchdogConfig

__all__ = [
    "ProposedOrder",
    "RiskContext",
    "Verdict",
    "Watchdog",
    "WatchdogConfig",
    "pretrade_check",
]
