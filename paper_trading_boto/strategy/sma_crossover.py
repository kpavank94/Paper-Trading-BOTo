"""Moving-average crossover strategy on OHLCV bars.

Rewrite of the original polling version.  Differences that matter:

* Operates on bar closes, not 5-second snapshot polls, so the windows
  mean what they say.
* Signals on actual *crossovers* (short MA crossing the long MA between
  consecutive bars), not on the level comparison the old code used —
  which re-entered immediately after every risk-manager exit while the
  short MA merely remained above the long MA.
* Warms up from history so it can trade from the first live bar.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

from ..events import Bar, Signal, SignalAction
from .base import Strategy


class SMACrossoverStrategy(Strategy):
    def __init__(self, symbol: str, short_window: int = 10, long_window: int = 30) -> None:
        super().__init__(symbol)
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self._closes: Deque[float] = deque(maxlen=long_window)
        self._prev_diff: Optional[float] = None  # short MA - long MA at previous bar

    def warmup_bars(self) -> int:
        return self.long_window

    def on_start(self, history: List[Bar]) -> None:
        for bar in history:
            self._update(bar.close)

    def _update(self, close: float) -> Optional[float]:
        """Push a close; return current (short - long) MA diff once warm."""
        self._closes.append(close)
        if len(self._closes) < self.long_window:
            return None
        closes = list(self._closes)
        short_ma = sum(closes[-self.short_window:]) / self.short_window
        long_ma = sum(closes) / self.long_window
        diff = short_ma - long_ma
        prev, self._prev_diff = self._prev_diff, diff
        if prev is None:
            return None  # need two warm bars to detect a cross
        crossed = (prev <= 0) != (diff <= 0)
        return diff if crossed else None

    def on_bar(self, bar: Bar) -> Optional[Signal]:
        crossed_diff = self._update(bar.close)
        if crossed_diff is None:
            return None
        action = SignalAction.ENTER_LONG if crossed_diff > 0 else SignalAction.EXIT_LONG
        return Signal(
            symbol=self.symbol,
            action=action,
            timestamp=bar.timestamp,
            reason=f"SMA{self.short_window}/{self.long_window} cross "
                   f"{'up' if crossed_diff > 0 else 'down'}",
        )
