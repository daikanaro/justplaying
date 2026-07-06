"""Event-driven backtest engine (BUILD_PLAN §4).

Single-threaded loop: MarketEvent -> SignalEvent -> OrderEvent -> FillEvent.
Fills default to next-bar-open; stops model gap-through; limits fill only on
trade-through >= 1 tick; accounting is exact to the cent with the
cash + marks == equity invariant checked on every event.
"""

from qt.backtest.engine import BacktestResult, Engine, EngineConfig, Strategy, StrategyContext
from qt.backtest.events import Bar
from qt.backtest.orders import LimitOrder, MarketOrder, Side, StopOrder
from qt.backtest.portfolio import AccountingError, Portfolio

__all__ = [
    "AccountingError",
    "BacktestResult",
    "Bar",
    "Engine",
    "EngineConfig",
    "LimitOrder",
    "MarketOrder",
    "Portfolio",
    "Side",
    "StopOrder",
    "Strategy",
    "StrategyContext",
]
