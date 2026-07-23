"""Historical bar feed backed by yfinance, for backtesting and warmup."""

from __future__ import annotations

import datetime as dt
from typing import Iterator, List, Optional

import pandas as pd

from ..events import Bar
from .base import DataFeed


def _frame_to_bars(frame: pd.DataFrame, symbol: str) -> List[Bar]:
    """Convert a yfinance OHLCV frame to Bars, dropping incomplete rows."""
    bars: List[Bar] = []
    # yfinance returns column MultiIndex when multiple tickers are requested;
    # normalize to flat columns for the single-ticker case.
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.xs(symbol, axis=1, level=-1)
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    for timestamp, row in frame.iterrows():
        ts = timestamp.to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0.0) or 0.0),
            )
        )
    return bars


class YFinanceFeed(DataFeed):
    """Finite historical feed over a date range.

    ``interval`` follows yfinance conventions ("1d", "1h", "5m", ...).
    Note yfinance limits intraday history (e.g. 5m bars to ~60 days).
    """

    def __init__(
        self,
        symbol: str,
        start: dt.date,
        end: dt.date,
        interval: str = "1d",
    ) -> None:
        self.symbol = symbol
        self.start = start
        self.end = end
        self.interval = interval
        self._all_bars: Optional[List[Bar]] = None
        self._warmup_consumed = 0

    def _download(self) -> List[Bar]:
        if self._all_bars is None:
            import yfinance as yf  # imported lazily; tests never need it

            frame = yf.download(
                self.symbol,
                start=self.start.isoformat(),
                end=self.end.isoformat(),
                interval=self.interval,
                auto_adjust=True,
                progress=False,
            )
            if frame is None or frame.empty:
                raise RuntimeError(
                    f"yfinance returned no data for {self.symbol} "
                    f"{self.start}..{self.end} interval={self.interval}"
                )
            self._all_bars = _frame_to_bars(frame, self.symbol)
        return self._all_bars

    def warmup(self, count: int) -> List[Bar]:
        """First ``count`` bars of the range are consumed as warmup."""
        self._warmup_consumed = count
        return self._download()[:count]

    def bars(self) -> Iterator[Bar]:
        """Bars after the warmup split (everything if warmup was never called)."""
        yield from self._download()[self._warmup_consumed:]


class CSVFeed(DataFeed):
    """Finite feed over a local OHLCV CSV (timestamp,open,high,low,close,volume).

    Used by tests and available for offline backtests.
    """

    def __init__(self, path: str, symbol: str, warmup_count: int = 0) -> None:
        frame = pd.read_csv(path, parse_dates=["timestamp"])
        frame = frame.rename(columns=str.capitalize).rename(
            columns={"Timestamp": "timestamp"}
        )
        frame = frame.set_index("timestamp")
        if frame.index.tz is None:
            frame.index = frame.index.tz_localize("UTC")
        all_bars = _frame_to_bars(frame, symbol)
        self._warmup = all_bars[:warmup_count]
        self._bars = all_bars[warmup_count:]

    def warmup(self, count: int) -> List[Bar]:
        return self._warmup[-count:] if count else []

    def bars(self) -> Iterator[Bar]:
        yield from self._bars
