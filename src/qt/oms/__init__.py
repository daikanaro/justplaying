"""Order management system (BUILD_PLAN slice 4.5).

Money-path invariants live in types and state machines, not conventions:
- the order state machine rejects illegal transitions (qt.oms.state),
- duplicate submits are suppressed by client-order-id idempotency
  (qt.oms.submitter), with bounded backoff — never a retry storm,
- reconciliation mismatches write the HALT flag and the engine refuses to
  start while it exists; re-arm is a manual owner action (qt.oms.halt),
- native stops can be created and ratcheted but never widened (qt.oms.stops).
"""

from qt.oms.halt import HaltError, require_not_halted, write_halt
from qt.oms.journal import OrderJournal
from qt.oms.state import IllegalTransitionError, OrderRecord, OrderState
from qt.oms.submitter import OrderSubmitter

__all__ = [
    "HaltError",
    "IllegalTransitionError",
    "OrderJournal",
    "OrderRecord",
    "OrderState",
    "OrderSubmitter",
    "require_not_halted",
    "write_halt",
]
