"""Telegram alerter tests — hermetic (mock transport, env manipulation)."""

import httpx
import pytest

from qt.risk.telegram import (
    CHAT_ID_ENV,
    TOKEN_ENV,
    TelegramAlerter,
    TelegramConfigError,
    daily_summary,
)


def make_alerter(handler: httpx.MockTransport) -> TelegramAlerter:
    return TelegramAlerter("tok123", "chat456", client=httpx.Client(transport=handler))


def test_alert_posts_to_bot_api() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    alerter = make_alerter(httpx.MockTransport(handler))
    alerter.alert("halt: something happened")
    (request,) = seen
    assert request.url.path == "/bottok123/sendMessage"
    assert b"halt: something happened" in request.content
    assert alerter.delivery_failures == 0


def test_http_error_counted_never_raised() -> None:
    alerter = make_alerter(httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    alerter.alert("message")  # must not raise into the money path
    assert alerter.delivery_failures == 1


def test_transport_error_counted_never_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    alerter = make_alerter(httpx.MockTransport(handler))
    alerter.alert("message")
    alerter.alert("second")
    assert alerter.delivery_failures == 2


def test_from_env_requires_owner_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv(CHAT_ID_ENV, raising=False)
    with pytest.raises(TelegramConfigError, match="OWNER ACTION"):
        TelegramAlerter.from_env()
    monkeypatch.setenv(TOKEN_ENV, "tok")
    with pytest.raises(TelegramConfigError, match="OWNER ACTION"):
        TelegramAlerter.from_env()  # chat id still missing
    monkeypatch.setenv(CHAT_ID_ENV, "chat")
    assert TelegramAlerter.from_env() is not None


def test_empty_credentials_rejected() -> None:
    with pytest.raises(TelegramConfigError, match="non-empty"):
        TelegramAlerter("", "chat")


def test_daily_summary_format() -> None:
    text = daily_summary(
        session_date="2026-07-06",
        equity_cents=9_996_270,
        day_pnl_cents=-3_730,
        fills=4,
        rejects=1,
        positions={"MES": 2, "M2K": 0},
        drawdown_pct=-0.0125,
    )
    assert "2026-07-06" in text
    assert "$99,962.70" in text
    assert "-37.30 today" in text
    assert "-1.25%" in text
    assert "fills: 4, rejects: 1" in text
    assert "MES:+2" in text
    assert "M2K" not in text.split("positions:")[1]  # flat symbols omitted


def test_daily_summary_flat_book() -> None:
    text = daily_summary("2026-07-06", 10_000_000, 0, 0, 0, {}, 0.0)
    assert "positions: flat" in text
