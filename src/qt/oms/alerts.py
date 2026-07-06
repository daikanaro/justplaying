"""Alert interface. The Telegram implementation arrives in slice 4.6 (the
token is an owner item, §6); until then LogAlerter records everything."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("qt.oms")


class Alerter(Protocol):
    def alert(self, message: str) -> None: ...


class LogAlerter:
    """Stdlib-logging alerter; also keeps an in-memory trail for tests."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def alert(self, message: str) -> None:
        self.messages.append(message)
        logger.warning("ALERT: %s", message)
