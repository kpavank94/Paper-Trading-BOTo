"""Position and PnL tracking, driven exclusively by confirmed fills.

Port of the original ``cost_basis.py`` with two correctness changes:

* Positions update only from :class:`~paper_trading_boto.events.Fill`
  objects delivered by a broker — never from orders that were merely
  submitted (the old code updated state optimistically at the last
  polled price).
* Short positions are handled correctly.  The original ``Position.update``
  realized PnL against a stale long average cost when selling more than
  held, and buy-to-cover never realized short PnL at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .events import Fill, Side


@dataclass
class Position:
    """Signed position with average cost. quantity > 0 long, < 0 short."""

    quantity: int = 0
    avg_cost: float = 0.0

    def apply_fill(self, side: Side, qty: int, price: float) -> float:
        """Apply a fill and return realized PnL (0.0 if none was realized).

        Handles all transitions: opening/adding, reducing, closing, and
        flipping through zero (the closing portion realizes PnL, the
        remainder opens a fresh position at the fill price).
        """
        signed = qty if side is Side.BUY else -qty
        realized = 0.0

        if self.quantity == 0 or (self.quantity > 0) == (signed > 0):
            # Opening or adding to an existing position: average the cost.
            total = self.avg_cost * abs(self.quantity) + price * abs(signed)
            self.quantity += signed
            self.avg_cost = total / abs(self.quantity)
            return 0.0

        # Fill opposes the current position: realize PnL on the closed part.
        closed = min(abs(signed), abs(self.quantity))
        if self.quantity > 0:
            realized = (price - self.avg_cost) * closed        # long: sell above cost gains
        else:
            realized = (self.avg_cost - price) * closed        # short: cover below cost gains

        self.quantity += signed
        if self.quantity == 0:
            self.avg_cost = 0.0
        elif abs(signed) > closed:
            # Flipped through zero: remainder is a new position at fill price.
            self.avg_cost = price
        return realized


@dataclass
class Portfolio:
    """Tracks positions, cash and realized PnL across symbols from fills."""

    initial_cash: float = 100_000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    fills: List[Fill] = field(default_factory=list)
    realized_pnl: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def apply_fill(self, fill: Fill) -> float:
        """Record a fill; returns realized PnL from this fill."""
        position = self.positions.setdefault(fill.symbol, Position())
        realized = position.apply_fill(fill.side, fill.quantity, fill.price)
        signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
        self.cash -= signed * fill.price + fill.commission
        self.fills.append(fill)
        self.realized_pnl[fill.symbol] = self.realized_pnl.get(fill.symbol, 0.0) + realized
        return realized

    def quantity(self, symbol: str) -> int:
        position = self.positions.get(symbol)
        return position.quantity if position else 0

    def avg_cost(self, symbol: str) -> Optional[float]:
        position = self.positions.get(symbol)
        if position and position.quantity != 0:
            return position.avg_cost
        return None

    def unrealized_pnl(self, symbol: str, current_price: float) -> float:
        position = self.positions.get(symbol)
        if not position or position.quantity == 0:
            return 0.0
        return (current_price - position.avg_cost) * position.quantity

    def total_realized_pnl(self) -> float:
        return sum(self.realized_pnl.values())

    def equity(self, prices: Dict[str, float]) -> float:
        """Cash plus mark-to-market value of open positions."""
        value = self.cash
        for symbol, position in self.positions.items():
            if position.quantity != 0:
                value += position.quantity * prices[symbol]
        return value

    def summary(self) -> Dict[str, dict]:
        return {
            symbol: {
                "quantity": position.quantity,
                "avg_cost": position.avg_cost,
                "realized_pnl": self.realized_pnl.get(symbol, 0.0),
            }
            for symbol, position in self.positions.items()
        }
