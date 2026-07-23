"""Broker interface.

A broker accepts :class:`~paper_trading_boto.events.OrderRequest` objects
and reports executions back through a fill callback.  The engine and
strategies never talk to a broker implementation directly beyond this
interface, which is what lets the same strategy code run against the
:class:`~paper_trading_boto.broker.sim.SimulatedBroker` in backtests and
:class:`~paper_trading_boto.broker.ibkr.IBKRBroker` in live paper trading.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from ..events import Fill, OrderRequest

FillCallback = Callable[[Fill], None]


class Broker(ABC):
    """Abstract broker: order submission, positions and account equity."""

    def __init__(self) -> None:
        self._fill_callbacks: List[FillCallback] = []

    def on_fill(self, callback: FillCallback) -> None:
        """Register a callback invoked for every confirmed fill."""
        self._fill_callbacks.append(callback)

    def _emit_fill(self, fill: Fill) -> None:
        for callback in self._fill_callbacks:
            callback(fill)

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> Optional[str]:
        """Submit an order; returns a broker order id, or None on rejection.

        Fills are reported asynchronously via ``on_fill`` callbacks —
        callers must not assume the order executed just because an id
        was returned.
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order by id (no-op if already done)."""

    @abstractmethod
    def positions(self) -> Dict[str, int]:
        """Current signed position quantity per symbol, per the broker."""

    @abstractmethod
    def equity(self) -> float:
        """Current account equity (cash + market value of positions)."""
