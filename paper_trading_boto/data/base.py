"""Data feed interface: historical warmup plus an iterator of bars.

Backtest feeds iterate a finite historical range; live feeds block on
new bars and end when the session is stopped.  Either way the engine
consumes the same two methods, so it cannot tell backtest from live.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List

from ..events import Bar


class DataFeed(ABC):
    @abstractmethod
    def warmup(self, count: int) -> List[Bar]:
        """Return up to ``count`` historical bars preceding the feed start."""

    @abstractmethod
    def bars(self) -> Iterator[Bar]:
        """Yield bars in chronological order until exhausted or stopped."""

    def stop(self) -> None:
        """Ask a live feed to stop yielding; no-op for historical feeds."""
