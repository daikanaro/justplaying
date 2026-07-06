"""Telegram alerter (§4.6): fills, rejects, halts, disconnects, daily summary.

The bot token and chat id are OWNER items (§6), provided via environment
variables and stored outside the repo. Alert delivery failures degrade to
logging and are counted — an alerting outage must never take down or block
the money path.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("qt.risk.telegram")

TOKEN_ENV = "QT_TELEGRAM_TOKEN"
CHAT_ID_ENV = "QT_TELEGRAM_CHAT_ID"
_API = "https://api.telegram.org"


class TelegramConfigError(Exception):
    """Token/chat id missing — an OWNER item (§6), never stubbed."""


class TelegramAlerter:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None) -> None:
        if not token or not chat_id:
            msg = "TelegramAlerter requires a non-empty token and chat_id"
            raise TelegramConfigError(msg)
        self._token = token
        self._chat_id = chat_id
        self._client = client or httpx.Client(timeout=10.0)
        self.delivery_failures = 0

    @classmethod
    def from_env(cls) -> TelegramAlerter:
        token = os.environ.get(TOKEN_ENV, "")
        chat_id = os.environ.get(CHAT_ID_ENV, "")
        if not token or not chat_id:
            msg = (
                f"OWNER ACTION (§6): set {TOKEN_ENV} and {CHAT_ID_ENV} (bot token stored "
                "outside the repo). No stub tokens — alerts either work or we say they don't."
            )
            raise TelegramConfigError(msg)
        return cls(token, chat_id)

    def alert(self, message: str) -> None:
        """Send; on ANY failure, log and count — never raise into the caller."""
        try:
            response = self._client.post(
                f"{_API}/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": message},
            )
            if response.status_code != httpx.codes.OK:
                self.delivery_failures += 1
                logger.error("telegram alert failed (HTTP %s): %s", response.status_code, message)
        except httpx.HTTPError as exc:
            self.delivery_failures += 1
            logger.error("telegram alert failed (%s): %s", exc, message)


def daily_summary(  # noqa: PLR0913 - one argument per summary line
    session_date: str,
    equity_cents: int,
    day_pnl_cents: int,
    fills: int,
    rejects: int,
    positions: dict[str, int],
    drawdown_pct: float,
) -> str:
    """The §4.6 daily summary message, one screen, no scrolling."""
    open_positions = ", ".join(f"{s}:{q:+d}" for s, q in sorted(positions.items()) if q) or "flat"
    return (
        f"QT daily summary {session_date}\n"
        f"equity: ${equity_cents / 100:,.2f} ({day_pnl_cents / 100:+,.2f} today)\n"
        f"drawdown from HWM: {drawdown_pct:.2%}\n"
        f"fills: {fills}, rejects: {rejects}\n"
        f"positions: {open_positions}"
    )
