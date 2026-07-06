"""Scripted, repeatable chaos drills (§4.5 acceptance). Requires a running
IB Gateway with a paper login (OWNER item §6) — each drill exits with code 2
and an owner-action message when the Gateway is unreachable.

  a  kill Gateway mid-order   -> on restart, state reconciles, zero unexplained diffs
  b  kill engine mid-session  -> restart reconciles journal == broker
  c  duplicate submit         -> suppressed by client-order-id idempotency
  d  forced reject            -> bounded backoff, one alert, no retry storm

Drills a/b intentionally PAUSE and tell the operator what to kill; they are
theater with assertions, not magic — the assertions run on the restart side.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from qt.oms.alerts import LogAlerter
from qt.oms.halt import HaltError
from qt.oms.ibkr_adapter import GatewayUnavailableError, IbkrOms
from qt.oms.journal import OrderJournal
from qt.oms.submitter import OrderIntent, OrderSubmitter, PlacementError, SubmitOutcome

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNAL = REPO_ROOT / "data" / "journal" / "orders.jsonl"
HALT = REPO_ROOT / "HALT"


def _connect(host: str, port: int) -> IbkrOms:
    oms = IbkrOms(OrderJournal(JOURNAL), HALT, LogAlerter(), host=host, port=port)
    try:
        asyncio.run(oms.connect())
    except GatewayUnavailableError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except HaltError as exc:
        print(f"HALTED: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    return oms


def drill_a(host: str, port: int) -> int:
    print("DRILL A — kill Gateway mid-order")
    print("1. This drill connects and prints instructions; run it TWICE:")
    print("   pass 1: while an order is working, kill IB Gateway (task manager).")
    print("   pass 2: restart Gateway, run again — connect() reconciles or halts.")
    oms = _connect(host, port)
    print("connected; journal==broker reconciliation PASSED (zero unexplained diffs)")
    oms.disconnect()
    return 0


def drill_b(host: str, port: int) -> int:
    print("DRILL B — kill engine mid-session")
    print("Kill this process at any point after connect; re-run to prove the")
    print("restart path reconciles the journal against the broker.")
    oms = _connect(host, port)
    print("reconnected; journal==broker reconciliation PASSED")
    time.sleep(5)  # window for the operator to kill the process
    oms.disconnect()
    return 0


def drill_c(host: str, port: int) -> int:
    print("DRILL C — duplicate submit suppressed by idempotency")
    _connect(host, port)  # gateway + reconciliation gate
    journal = OrderJournal(JOURNAL)
    alerter = LogAlerter()

    placed: list[str] = []

    def place(intent: OrderIntent, order_id: str) -> None:
        placed.append(order_id)  # drill-level fake; the unit tests cover the real path

    submitter = OrderSubmitter(journal, place, alerter, time.sleep)
    intent = OrderIntent("drill-c/MES/probe", "MES", "buy", 1)
    first = submitter.submit(intent)
    second = submitter.submit(intent)  # the DUPLICATE
    assert first is SubmitOutcome.PLACED, first
    assert second is SubmitOutcome.DUPLICATE_SUPPRESSED, second
    assert len(placed) == 1, placed
    print("duplicate suppressed; exactly one placement went out")
    return 0


def drill_d(host: str, port: int) -> int:
    print("DRILL D — forced reject: bounded backoff, one alert, no storm")
    _connect(host, port)
    journal = OrderJournal(JOURNAL)
    alerter = LogAlerter()
    attempts: list[float] = []

    def always_reject(intent: OrderIntent, order_id: str) -> None:
        attempts.append(time.monotonic())
        msg = "forced reject (drill)"
        raise PlacementError(msg)

    submitter = OrderSubmitter(
        journal, always_reject, alerter, time.sleep, max_attempts=3, backoff_base_s=1.0
    )
    outcome = submitter.submit(OrderIntent("drill-d/MES/probe", "MES", "buy", 1))
    assert outcome is SubmitOutcome.GAVE_UP, outcome
    expected_attempts = 3  # matches max_attempts above
    assert len(attempts) == expected_attempts, f"expected 3 bounded attempts, got {len(attempts)}"
    assert len(alerter.messages) == 1, alerter.messages
    print(f"gave up after {len(attempts)} attempts, 1 alert — no retry storm")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drill", choices=["a", "b", "c", "d"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    args = parser.parse_args()
    return {"a": drill_a, "b": drill_b, "c": drill_c, "d": drill_d}[args.drill](
        args.host, args.port
    )


if __name__ == "__main__":
    raise SystemExit(main())
