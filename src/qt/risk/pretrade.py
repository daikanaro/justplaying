"""Pre-trade checks — the single choke point (§4.6).

Every outbound order object passes through :func:`pretrade_check`; there is no
second path to the broker. A rejection reports EVERY failed check, not just
the first, so the operator sees the whole picture in one alert.

Checks (§2 constants from risk.yaml):
- whitelist,
- reduce-only while the daily loss halt is active (exits always allowed),
- per-symbol contract caps on the RESULTING position,
- price collar: limit/stop prices within price_collar_pct of the last mark,
- gross notional across all positions after the fill,
- per-trade risk to the stop within per_trade_risk_max.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from qt.config.schemas import InstrumentsConfig, RiskConfig


@dataclass(frozen=True)
class ProposedOrder:
    symbol: str
    quantity: int  # signed delta to the position
    price: float | None = None  # None = market order (no collar to check)
    stop_price: float | None = None  # protective stop, for the per-trade risk check


@dataclass(frozen=True)
class RiskContext:
    risk: RiskConfig
    instruments: InstrumentsConfig
    equity_cents: int
    positions: dict[str, int]  # signed contracts per symbol
    last_marks: dict[str, float]  # last mark per symbol (all open + traded symbols)
    daily_halted: bool = False


@dataclass(frozen=True)
class Verdict:
    approved: bool
    reasons: list[str] = field(default_factory=list)  # empty when approved


def _is_entry(order: ProposedOrder, ctx: RiskContext) -> bool:
    """An order that grows or flips the position is an entry; pure reductions
    toward flat are exits and stay allowed under the daily halt (§2)."""
    current = ctx.positions.get(order.symbol, 0)
    resulting = current + order.quantity
    return abs(resulting) > abs(current) or (current != 0 and resulting * current < 0)


def pretrade_check(order: ProposedOrder, ctx: RiskContext) -> Verdict:  # noqa: PLR0912 - the checklist, in one visible place
    reasons: list[str] = []
    symbol = order.symbol
    spec = ctx.instruments.instruments.get(symbol)
    mark = ctx.last_marks.get(symbol)

    entry = _is_entry(order, ctx)

    if order.quantity == 0:
        reasons.append("zero-quantity order")
    if spec is None:
        reasons.append(f"{symbol}: no instrument spec")
    if entry and symbol not in ctx.risk.instrument_whitelist:
        # Entries only: a position in a de-whitelisted symbol must stay closable.
        reasons.append(f"{symbol}: not whitelisted")
    if mark is None:
        reasons.append(f"{symbol}: no last mark for collar/notional checks")

    if ctx.daily_halted and entry:
        reasons.append("daily loss halt active: new entries blocked (exits allowed)")

    if entry and order.stop_price is None:
        # Both strategies carry an initial protective stop (§3); an entry with
        # no declared stop would silently skip the per-trade-risk check below.
        reasons.append(f"{symbol}: entry without a declared protective stop")

    resulting = ctx.positions.get(symbol, 0) + order.quantity
    cap = ctx.risk.max_contracts.get(symbol, 0)
    if abs(resulting) > cap:
        reasons.append(f"{symbol}: resulting position {resulting} exceeds cap {cap}")

    # Collar applies to ORDER prices only. Protective stop triggers are
    # away-from-market by design (2.5-3 x ATR routinely exceeds 1%);
    # collaring them would reject every plan-mandated stop. Their size is
    # policed by the per-trade risk check instead.
    if (
        mark is not None
        and mark > 0
        and order.price is not None
        and abs(order.price - mark) / mark > ctx.risk.price_collar_pct
    ):
        reasons.append(
            f"{symbol}: price {order.price} is >{ctx.risk.price_collar_pct:.1%} "
            f"from last mark {mark}"
        )

    if spec is not None and mark is not None:
        # Gross notional across ALL positions as they would stand after the fill.
        notional_cents = 0.0
        for sym, quantity in {**ctx.positions, symbol: resulting}.items():
            sym_spec = ctx.instruments.instruments.get(sym)
            sym_mark = ctx.last_marks.get(sym)
            if sym_spec is None or sym_mark is None:
                if quantity != 0:
                    reasons.append(f"{sym}: open position lacks spec/mark for notional check")
                continue
            notional_cents += abs(quantity) * sym_mark * sym_spec.dollars_per_point * 100.0
        limit_cents = ctx.risk.gross_notional_max_x_equity * ctx.equity_cents
        if notional_cents > limit_cents:
            reasons.append(
                f"gross notional {notional_cents / 100:.2f} exceeds "
                f"{ctx.risk.gross_notional_max_x_equity}x equity ({limit_cents / 100:.2f})"
            )

        if order.stop_price is not None and entry:
            reference = order.price if order.price is not None else mark
            risk_cents = (
                abs(reference - order.stop_price)
                * abs(order.quantity)
                * spec.dollars_per_point
                * 100.0
            )
            budget_cents = ctx.risk.per_trade_risk_max * ctx.equity_cents
            if risk_cents > budget_cents:
                reasons.append(
                    f"{symbol}: per-trade risk {risk_cents / 100:.2f} exceeds "
                    f"{ctx.risk.per_trade_risk_max:.2%} of equity ({budget_cents / 100:.2f})"
                )

    return Verdict(approved=not reasons, reasons=reasons)
