"""Independent watchdog process (§4.6). Run as its OWN Task Scheduler job —
never inside the engine (docs/windows_ops.md).

Each cycle: check the engine heartbeat (dead-man alert on stall), pull equity
from the broker, and run the §2 daily-halt / kill logic. Requires IB Gateway
(OWNER item §6); exits 2 with an owner-action message when unreachable.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from qt.config import RiskConfig, load_config
from qt.oms.alerts import Alerter, LogAlerter
from qt.risk.heartbeat import DeadManSwitch
from qt.risk.telegram import TelegramAlerter, TelegramConfigError
from qt.risk.watchdog import Watchdog, WatchdogAction, WatchdogConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = REPO_ROOT / "data" / "journal"


def make_alerter() -> Alerter:
    try:
        return TelegramAlerter.from_env()
    except TelegramConfigError as exc:
        print(f"WARNING: {exc}; falling back to log-only alerts", file=sys.stderr)
        return LogAlerter()


async def broker_equity_cents(host: str, port: int) -> int:
    from ib_async import IB  # noqa: PLC0415 - gateway-only path

    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=23, timeout=10.0)
    except (TimeoutError, OSError) as exc:
        msg = (
            f"cannot reach IB Gateway at {host}:{port} — OWNER ACTION (§6): "
            "paper login + running Gateway required"
        )
        print(f"BLOCKED: {msg}", file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        summary = await ib.accountSummaryAsync()
        for row in summary:
            if row.tag == "NetLiquidation":
                return round(float(row.value) * 100)
        print("BLOCKED: NetLiquidation missing from account summary", file=sys.stderr)
        raise SystemExit(2)
    finally:
        ib.disconnect()


class GatewayBrokerActions:
    """Emergency actions via a dedicated connection (kill path, §2)."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def cancel_all(self) -> None:
        asyncio.run(self._cancel_all())

    def flatten_all(self) -> None:
        asyncio.run(self._flatten_all())

    async def _cancel_all(self) -> None:
        from ib_async import IB  # noqa: PLC0415

        ib = IB()
        await ib.connectAsync(self._host, self._port, clientId=24, timeout=10.0)
        try:
            ib.reqGlobalCancel()  # type: ignore[no-untyped-call]
        finally:
            ib.disconnect()

    async def _flatten_all(self) -> None:
        from ib_async import IB, MarketOrder  # noqa: PLC0415

        ib = IB()
        await ib.connectAsync(self._host, self._port, clientId=25, timeout=10.0)
        try:
            for position in ib.positions():
                if not position.position:
                    continue
                action = "SELL" if position.position > 0 else "BUY"
                order = MarketOrder(action, abs(int(position.position)))
                order.orderRef = "QT-KILL-FLATTEN"
                ib.placeOrder(position.contract, order)
            await asyncio.sleep(2.0)  # let the orders go out before disconnecting
        finally:
            ib.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--interval", type=float, default=30.0, help="cycle seconds")
    parser.add_argument("--once", action="store_true", help="single cycle (smoke test)")
    args = parser.parse_args()

    risk = load_config(REPO_ROOT / "config" / "risk.yaml", RiskConfig)
    alerter = make_alerter()
    watchdog = Watchdog(
        risk,
        WatchdogConfig(
            state_path=RUNTIME / "watchdog_state.json",
            daily_halt_flag=RUNTIME / "DAILY_HALT",
            halt_flag=REPO_ROOT / "HALT",
        ),
        GatewayBrokerActions(args.host, args.port),
        alerter,
    )
    dead_man = DeadManSwitch(RUNTIME / "engine.heartbeat", alerter)

    while True:
        dead_man.check()
        equity = asyncio.run(broker_equity_cents(args.host, args.port))
        action = watchdog.tick(equity, datetime.now(UTC).date())
        if action is WatchdogAction.KILL:
            print("KILL executed; HALT flag written; watchdog exiting", file=sys.stderr)
            return 1
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
