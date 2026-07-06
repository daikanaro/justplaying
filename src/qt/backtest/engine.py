"""The event loop (§4): MarketEvent -> SignalEvent -> OrderEvent -> FillEvent.

Bar-t semantics, fixed and hand-computable (KA-2 depends on this order):

1. OPEN phase — orders scheduled at earlier bars whose delay has elapsed fill
   as market orders at open(t) ± session-aware slippage.
2. INTRABAR phase — resting protective stops are evaluated against bar t
   (gap-through modeled). A stop set at the close of t-1 is live during t;
   a stop can fire the same bar its entry filled (conservative).
3. CLOSE phase — mark-to-market at close(t); funding hook (inert); margin
   check; strategy.on_bar(ctx) emits target positions; the delta between
   targets and current positions is scheduled to execute at t + latency_bars
   (default 1 = next-bar-open, §3 entry timing).

Stops are engine-managed and structurally cannot widen: StrategyContext.set_stop
raises StopWideningError on any attempt (the §3 invariant, enforced in the API
not by convention). Stops always cover the whole current position and are
cleared when the position goes flat or flips.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import Protocol

from qt.backtest.events import Bar, FillEvent, MarketEvent, OrderEvent, SignalEvent
from qt.backtest.execution import ExecutionConfig, ExecutionSimulator
from qt.backtest.orders import MarketOrder, Side, StopOrder
from qt.backtest.portfolio import Portfolio
from qt.costs.model import CostModel


class EngineError(Exception):
    """Bad input data or an impossible engine state."""


class StopWideningError(Exception):
    """A strategy attempted to widen a protective stop. Structurally forbidden (§3)."""


@dataclass(frozen=True)
class EngineConfig:
    initial_cash_cents: int
    latency_bars: int = 1  # §4 latency mode: signal at T, fill at T+delta
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    def __post_init__(self) -> None:
        if self.latency_bars < 1:
            msg = (
                f"latency_bars must be >= 1 (same-bar fills are lookahead), got {self.latency_bars}"
            )
            raise EngineError(msg)


class StrategyContext:
    """The strategy's read view of the run plus the stop-management API."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @property
    def now(self) -> datetime:
        return self._engine.current_ts

    @property
    def index(self) -> int:
        return self._engine.current_index

    @property
    def equity_cents(self) -> int:
        return self._engine.portfolio.equity_cents

    def bars(self, symbol: str) -> list[Bar]:
        """All bars up to and including the current one."""
        return self._engine.bars_upto(symbol)

    def position(self, symbol: str) -> int:
        return self._engine.portfolio.quantity(symbol)

    def set_stop(self, symbol: str, price: float) -> None:
        self._engine.set_stop(symbol, price)

    def stop_level(self, symbol: str) -> float | None:
        order = self._engine.stops.get(symbol)
        return None if order is None else order.stop_price


class Strategy(Protocol):
    def on_bar(self, ctx: StrategyContext) -> dict[str, int]:
        """Return target contracts per symbol. Strategies never emit orders (§3)."""
        ...


@dataclass
class BacktestResult:
    equity_curve: list[tuple[datetime, int]]
    fills: list[FillEvent]
    signals: list[SignalEvent]
    margin_breaches: list[datetime]
    final_equity_cents: int


class Engine:
    def __init__(
        self,
        bars: dict[str, list[Bar]],
        strategy: Strategy,
        costs: CostModel,
        config: EngineConfig,
    ) -> None:
        _validate_bars(bars)
        self._bars = bars
        self._symbols = sorted(bars)
        self._timestamps = [b.ts for b in next(iter(bars.values()))]
        self._strategy = strategy
        self._costs = costs
        self._config = config
        self._execution = ExecutionSimulator(costs, config.execution)
        self.portfolio = Portfolio(costs, config.initial_cash_cents)
        self.stops: dict[str, StopOrder] = {}
        self._pending: list[tuple[int, OrderEvent]] = []  # (execute_at_index, order)
        self.current_index = -1
        self._last_event_ts: datetime | None = None

    # -- public API -------------------------------------------------------

    def run(self) -> BacktestResult:
        equity_curve: list[tuple[datetime, int]] = []
        fills: list[FillEvent] = []
        signals: list[SignalEvent] = []
        ctx = StrategyContext(self)
        for index, ts in enumerate(self._timestamps):
            self.current_index = index
            bars_now = {s: self._bars[s][index] for s in self._symbols}
            market_event = MarketEvent(ts, bars_now)
            self._observe(market_event.ts)

            fills.extend(self._open_phase(index, bars_now))
            fills.extend(self._intrabar_phase(bars_now))

            self.portfolio.mark_to_market(ts, {s: b.close for s, b in bars_now.items()})
            self.portfolio.accrue_funding(ts)
            self.portfolio.check_margin(ts)

            targets = self._strategy.on_bar(ctx)
            signal = SignalEvent(ts, dict(targets))
            signals.append(signal)
            self._schedule_orders(index, signal)

            equity_curve.append((ts, self.portfolio.equity_cents))
        return BacktestResult(
            equity_curve=equity_curve,
            fills=fills,
            signals=signals,
            margin_breaches=list(self.portfolio.margin_breaches),
            final_equity_cents=self.portfolio.equity_cents,
        )

    # -- engine internals ---------------------------------------------------

    @property
    def current_ts(self) -> datetime:
        return self._timestamps[self.current_index]

    def bars_upto(self, symbol: str) -> list[Bar]:
        if symbol not in self._bars:
            msg = f"unknown symbol {symbol!r}"
            raise EngineError(msg)
        return self._bars[symbol][: self.current_index + 1]

    def set_stop(self, symbol: str, price: float) -> None:
        quantity = self.portfolio.quantity(symbol)
        pending_qty = sum(o.quantity for _, o in self._pending if o.symbol == symbol)
        effective = quantity + pending_qty
        if effective == 0:
            msg = f"cannot set a stop on {symbol} with no position or pending entry"
            raise EngineError(msg)
        side = Side.SELL if effective > 0 else Side.BUY
        existing = self.stops.get(symbol)
        if existing is not None and existing.side is side:
            widening = (side is Side.SELL and price < existing.stop_price) or (
                side is Side.BUY and price > existing.stop_price
            )
            if widening:
                msg = (
                    f"{symbol}: stop {existing.stop_price} -> {price} widens the stop; "
                    "ratchets only (§3)"
                )
                raise StopWideningError(msg)
        self.stops[symbol] = StopOrder(
            symbol=symbol, side=side, quantity=max(abs(effective), 1), stop_price=price
        )

    def _open_phase(self, index: int, bars_now: dict[str, Bar]) -> list[FillEvent]:
        due = [(at, o) for at, o in self._pending if at <= index]
        self._pending = [(at, o) for at, o in self._pending if at > index]
        fills: list[FillEvent] = []
        for _, order_event in due:
            side = Side.BUY if order_event.quantity > 0 else Side.SELL
            order = MarketOrder(
                symbol=order_event.symbol, side=side, quantity=abs(order_event.quantity)
            )
            while order.remaining > 0:
                fill = self._execution.fill_market(
                    order, bars_now[order_event.symbol], order_event.reason
                )
                self._observe(fill.ts)
                self.portfolio.apply_fill(fill)
                fills.append(fill)
            self._sync_stop_quantity(order_event.symbol)
        return fills

    def _intrabar_phase(self, bars_now: dict[str, Bar]) -> list[FillEvent]:
        fills: list[FillEvent] = []
        for symbol in self._symbols:
            stop = self.stops.get(symbol)
            if stop is None or self.portfolio.quantity(symbol) == 0:
                continue
            while stop.remaining > 0:
                fill = self._execution.try_fill_stop(stop, bars_now[symbol], "stop")
                if fill is None:
                    break
                self._observe(fill.ts)
                self.portfolio.apply_fill(fill)
                fills.append(fill)
            if stop.remaining == 0 or self.portfolio.quantity(symbol) == 0:
                self.stops.pop(symbol, None)
        return fills

    def _schedule_orders(self, index: int, signal: SignalEvent) -> None:
        for symbol, target in signal.targets.items():
            if symbol not in self._bars:
                msg = f"strategy targeted unknown symbol {symbol!r}"
                raise EngineError(msg)
            pending_qty = sum(o.quantity for _, o in self._pending if o.symbol == symbol)
            delta = target - self.portfolio.quantity(symbol) - pending_qty
            if delta == 0:
                continue
            event = OrderEvent(ts=signal.ts, symbol=symbol, quantity=delta, reason="target")
            self._pending.append((index + self._config.latency_bars, event))
            current_dir = self.portfolio.quantity(symbol) + pending_qty + delta
            if current_dir == 0 or target == 0:
                self.stops.pop(symbol, None)  # going flat: stop travels with the position

    def _sync_stop_quantity(self, symbol: str) -> None:
        """Keep the resting stop covering the whole position after fills."""
        quantity = self.portfolio.quantity(symbol)
        stop = self.stops.get(symbol)
        if stop is None:
            return
        if quantity == 0 or (quantity > 0) != (stop.side is Side.SELL):
            self.stops.pop(symbol, None)
            return
        self.stops[symbol] = StopOrder(
            symbol=symbol, side=stop.side, quantity=abs(quantity), stop_price=stop.stop_price
        )

    def _observe(self, ts: datetime) -> None:
        """No event may move backward in time (§4.2 property)."""
        if self._last_event_ts is not None and ts < self._last_event_ts:
            msg = f"event time went backwards: {self._last_event_ts} -> {ts}"
            raise EngineError(msg)
        self._last_event_ts = ts


def _validate_bars(bars: dict[str, list[Bar]]) -> None:
    if not bars:
        msg = "no bar data supplied"
        raise EngineError(msg)
    reference: list[datetime] | None = None
    for symbol, series in bars.items():
        if not series:
            msg = f"{symbol}: empty bar series"
            raise EngineError(msg)
        timestamps = [b.ts for b in series]
        if any(nxt <= prev for prev, nxt in pairwise(timestamps)):
            msg = f"{symbol}: bar timestamps must be strictly increasing"
            raise EngineError(msg)
        if reference is None:
            reference = timestamps
        elif timestamps != reference:
            msg = f"{symbol}: bar timestamps not aligned across symbols"
            raise EngineError(msg)
