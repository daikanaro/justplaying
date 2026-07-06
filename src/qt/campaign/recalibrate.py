"""Cost-model recalibration SUGGESTIONS from real paper fills (§4.7).

Computes observed commission per side and observed slippage ticks by session
(RTH/ETH) and reports them next to the configured values. It deliberately
does NOT edit instruments.yaml — config changes are reviewed by a human with
the diff in front of them, never applied by a script.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qt.costs.model import CostModel
from qt.data.sessions import is_rth
from qt.oms.journal import FillRecord
from qt.risk.nightly import StatementTrade


@dataclass(frozen=True)
class CostSuggestions:
    n_fills: int
    n_reference_priced: int
    observed_commission_per_side_cents: float | None
    configured_commission_per_side_cents: float
    observed_rth_slippage_ticks: float | None
    configured_rth_slippage_ticks: int
    observed_eth_slippage_ticks: float | None
    configured_eth_slippage_ticks: int

    def to_text(self) -> str:
        def fmt(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.2f}"

        return (
            "cost-model recalibration suggestions (review, then edit instruments.yaml "
            "by hand if warranted):\n"
            f"  commission/side cents: observed {fmt(self.observed_commission_per_side_cents)} "
            f"vs configured {self.configured_commission_per_side_cents:.0f}\n"
            f"  RTH slippage ticks:    observed {fmt(self.observed_rth_slippage_ticks)} "
            f"vs configured {self.configured_rth_slippage_ticks}\n"
            f"  ETH slippage ticks:    observed {fmt(self.observed_eth_slippage_ticks)} "
            f"vs configured {self.configured_eth_slippage_ticks}\n"
            f"  sample: {self.n_fills} fills, {self.n_reference_priced} reference-priced"
        )


def suggest_costs(
    fills: list[FillRecord],
    statement_trades: list[StatementTrade],
    costs: CostModel,
    symbol: str,
) -> CostSuggestions:
    spec = costs.spec(symbol)
    symbol_fills = [f for f in fills if f.symbol == symbol]

    contracts = sum(abs(t.quantity) for t in statement_trades if t.symbol == symbol)
    commissions = sum(t.commission_cents for t in statement_trades if t.symbol == symbol)
    observed_commission = commissions / contracts if contracts else None

    rth: list[float] = []
    eth: list[float] = []
    for fill in symbol_fills:
        if fill.reference_price is None:
            continue
        sign = 1 if fill.side == "buy" else -1
        ticks = sign * (fill.price - fill.reference_price) / spec.tick_size
        target = rth if is_rth(datetime.fromisoformat(fill.ts_utc)) else eth
        target.append(ticks)

    return CostSuggestions(
        n_fills=len(symbol_fills),
        n_reference_priced=len(rth) + len(eth),
        observed_commission_per_side_cents=observed_commission,
        configured_commission_per_side_cents=float(spec.commission_per_side_cents),
        observed_rth_slippage_ticks=(sum(rth) / len(rth)) if rth else None,
        configured_rth_slippage_ticks=costs.slippage_ticks_rth(),
        observed_eth_slippage_ticks=(sum(eth) / len(eth)) if eth else None,
        configured_eth_slippage_ticks=costs.slippage_ticks_eth(),
    )
