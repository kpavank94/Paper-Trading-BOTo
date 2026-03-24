"""
Cost basis and PnL tracking for Paper Trading BOTo.

This module provides data structures for recording trades and computing
both realized and unrealized profit and loss.  Accurate cost basis
analysis is important for evaluating strategy performance and for tax
reporting【362023408974584†L165-L196】.  The ``CostBasisTracker`` class
maintains an internal ledger of trades and can output summaries for
reporting.

Trades are recorded via the ``record_trade`` method.  When positions
are closed, realized profit/loss is computed using average cost.  The
tracker also calculates the current cost basis and unrealized PnL for
open positions.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TradeRecord:
    symbol: str
    action: str  # 'BUY' or 'SELL'
    quantity: int
    price: float
    timestamp: datetime.datetime


@dataclass
class Position:
    quantity: int = 0
    avg_cost: float = 0.0

    def update(self, action: str, qty: int, price: float) -> float:
        """Update position based on a trade and return realized PnL (if any)."""
        realized_pnl = 0.0
        if action == "BUY":
            total_cost = self.avg_cost * self.quantity + price * qty
            self.quantity += qty
            if self.quantity != 0:
                self.avg_cost = total_cost / self.quantity
        elif action == "SELL":
            # Realized PnL = (sell price - avg cost) * qty
            realized_pnl = (price - self.avg_cost) * qty
            self.quantity -= qty
            if self.quantity < 0:
                # More sold than held, treat as flat; leftover quantity becomes new short
                self.avg_cost = price
            if self.quantity == 0:
                self.avg_cost = 0.0
        return realized_pnl


@dataclass
class CostBasisTracker:
    """Tracks cost basis and PnL for multiple symbols."""

    positions: Dict[str, Position] = field(default_factory=dict)
    trade_history: List[TradeRecord] = field(default_factory=list)
    realized_pnl: Dict[str, float] = field(default_factory=dict)

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a trade and update cost basis."""
        position = self.positions.get(trade.symbol, Position())
        pnl = position.update(trade.action, trade.quantity, trade.price)
        self.positions[trade.symbol] = position
        self.trade_history.append(trade)
        self.realized_pnl[trade.symbol] = self.realized_pnl.get(trade.symbol, 0.0) + pnl

    def get_cost_basis(self, symbol: str) -> Optional[float]:
        position = self.positions.get(symbol)
        if position and position.quantity != 0:
            return position.avg_cost
        return None

    def get_unrealized_pnl(self, symbol: str, current_price: float) -> float:
        position = self.positions.get(symbol)
        if not position or position.quantity == 0:
            return 0.0
        return (current_price - position.avg_cost) * position.quantity

    def get_realized_pnl(self, symbol: str) -> float:
        return self.realized_pnl.get(symbol, 0.0)

    def summary(self) -> Dict[str, dict]:
        """Return summary of positions with cost basis and PnL."""
        summary: Dict[str, dict] = {}
        for symbol, position in self.positions.items():
            summary[symbol] = {
                "quantity": position.quantity,
                "avg_cost": position.avg_cost,
                "realized_pnl": self.realized_pnl.get(symbol, 0.0),
            }
        return summary