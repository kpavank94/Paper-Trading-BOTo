"""Strategy base class.

Strategies are pure signal generators: they see bars and return
:class:`~paper_trading_boto.events.Signal` intents.  They hold no broker
handle, place no orders and track no cash — sizing and execution belong
to the risk layer and engine.  This is what makes a strategy testable
with plain lists of bars and identical between backtest and live runs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..events import Bar, Signal


class Strategy(ABC):
    """Base class for bar-driven strategies."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def warmup_bars(self) -> int:
        """How many historical bars the strategy needs before its first signal.

        The engine feeds this many bars through :meth:`on_start` so the
        strategy is live from the very first real-time bar instead of
        waiting to accumulate state (the old bot idled for
        ``long_window`` polls before it could trade).
        """
        return 0

    def on_start(self, history: List[Bar]) -> None:
        """Called once with warmup history before the first live bar."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> Optional[Signal]:
        """Process one bar; return a Signal or None."""

    def on_finish(self) -> None:
        """Called once after the run ends."""
