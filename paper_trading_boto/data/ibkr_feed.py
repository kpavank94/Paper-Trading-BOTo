"""Live bar feed from IBKR: historical warmup + streaming 5-second bars
aggregated to the requested bar size.

Replaces the old snapshot-poll loop.  ``reqHistoricalData`` supplies
warmup bars so strategies are live immediately; ``reqRealTimeBars``
streams true 5s OHLCV bars which we aggregate into ``bar_seconds``
buckets (IBKR only streams 5s natively).
"""

from __future__ import annotations

import datetime as dt
import logging
import queue
from typing import Iterator, List, Optional

from ib_async import IB, RealTimeBar, Stock

from ..events import Bar
from .base import DataFeed

logger = logging.getLogger(__name__)


class IBKRFeed(DataFeed):
    def __init__(
        self,
        ib: IB,
        symbol: str,
        bar_seconds: int = 60,
        exchange: str = "SMART",
        currency: str = "USD",
        use_rth: bool = True,
    ) -> None:
        if bar_seconds % 5 != 0 or bar_seconds < 5:
            raise ValueError("bar_seconds must be a positive multiple of 5")
        self.ib = ib
        self.symbol = symbol
        self.bar_seconds = bar_seconds
        self.contract = Stock(symbol, exchange, currency)
        self.use_rth = use_rth
        self._queue: "queue.Queue[Optional[Bar]]" = queue.Queue()
        self._stopped = False
        self._bars_subscription = None
        # Aggregation state
        self._bucket: List[RealTimeBar] = []
        self._bucket_start: Optional[dt.datetime] = None

    # -- Warmup ---------------------------------------------------------------

    def warmup(self, count: int) -> List[Bar]:
        if count <= 0:
            return []
        # Request a generous window and trim; barSizeSetting must match
        # the live aggregation size.
        bar_size = self._ib_bar_size()
        seconds_needed = count * self.bar_seconds * 3  # padding for closed hours
        duration = f"{max(seconds_needed, 300)} S"
        if seconds_needed > 86_400:
            duration = f"{(seconds_needed // 86_400) + 1} D"
        raw = self.ib.reqHistoricalData(
            self.contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=self.use_rth,
            formatDate=2,  # UTC
        )
        bars = [
            Bar(
                symbol=self.symbol,
                timestamp=self._as_utc(b.date),
                open=float(b.open), high=float(b.high),
                low=float(b.low), close=float(b.close),
                volume=float(b.volume),
            )
            for b in raw
        ]
        logger.info("Warmup: %d/%d %s bars", min(len(bars), count), count, bar_size)
        return bars[-count:]

    def _ib_bar_size(self) -> str:
        if self.bar_seconds < 60:
            return f"{self.bar_seconds} secs"
        minutes = self.bar_seconds // 60
        return "1 min" if minutes == 1 else f"{minutes} mins"

    @staticmethod
    def _as_utc(value) -> dt.datetime:
        if isinstance(value, dt.datetime):
            ts = value
        else:  # date (daily bars)
            ts = dt.datetime.combine(value, dt.time())
        return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)

    # -- Streaming ---------------------------------------------------------------

    def bars(self) -> Iterator[Bar]:
        self._bars_subscription = self.ib.reqRealTimeBars(
            self.contract, 5, "TRADES", useRTH=self.use_rth
        )
        self._bars_subscription.updateEvent += self._on_rtb
        try:
            while not self._stopped:
                # Pump the ib_async event loop, then drain our queue.
                self.ib.sleep(0.25)
                try:
                    while True:
                        bar = self._queue.get_nowait()
                        if bar is None:
                            return
                        yield bar
                except queue.Empty:
                    continue
        finally:
            if self._bars_subscription is not None:
                self.ib.cancelRealTimeBars(self._bars_subscription)

    def stop(self) -> None:
        self._stopped = True
        self._queue.put(None)

    def _on_rtb(self, bars, has_new_bar: bool) -> None:
        if not has_new_bar or not bars:
            return
        rtb = bars[-1]
        start = self._as_utc(rtb.time)
        bucket_start = start - dt.timedelta(
            seconds=start.timestamp() % self.bar_seconds
        )
        if self._bucket_start is None:
            self._bucket_start = bucket_start
        if bucket_start != self._bucket_start:
            self._flush()
            self._bucket_start = bucket_start
        self._bucket.append(rtb)

    def _flush(self) -> None:
        if not self._bucket or self._bucket_start is None:
            return
        chunk = self._bucket
        self._bucket = []
        self._queue.put(
            Bar(
                symbol=self.symbol,
                timestamp=self._bucket_start,
                open=float(chunk[0].open_),
                high=max(float(b.high) for b in chunk),
                low=min(float(b.low) for b in chunk),
                close=float(chunk[-1].close),
                volume=sum(float(b.volume) for b in chunk),
            )
        )
