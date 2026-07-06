"""Trading-cost model. Single implementation (BUILD_PLAN §4): imported by the
backtester now and by the live executor in slice 4.5+. Never fork it."""

from qt.costs.model import CostModel

__all__ = ["CostModel"]
