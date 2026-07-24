"""Historical daily bars from the Alpaca market data API.

The previous design polled a single last price every few seconds and computed
"moving averages" over those ticks, so the averages had no fixed time meaning
and could not be reproduced offline. Strategies now consume OHLCV bars, which
makes the same code usable for both backtesting and live trading.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Sequence

import pandas as pd
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from .config import Settings

OHLCV = ["open", "high", "low", "close", "volume"]


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=OHLCV, index=pd.DatetimeIndex([], tz="UTC", name="timestamp")
    )


class MarketData:
    """Daily bar loader. Bars are split and dividend adjusted by default."""

    def __init__(self, settings: Settings) -> None:
        creds = settings.require_alpaca()
        self.settings = settings
        self.feed = DataFeed(creds.feed)
        self.timeframe = TimeFrame(1, TimeFrameUnit.Day)
        self.client = StockHistoricalDataClient(creds.api_key, creds.secret_key)

    def daily_bars(
        self,
        symbols: Sequence[str] | None = None,
        lookback_days: int | None = None,
        end: datetime | None = None,
    ) -> Dict[str, pd.DataFrame]:
        symbols = list(symbols or self.settings.symbols)
        end = end or datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days or self.settings.history_days)

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=self.timeframe,
            start=start,
            end=end,
            feed=self.feed,
            adjustment=Adjustment.ALL,
        )
        frame = self.client.get_stock_bars(request).df
        if frame.empty:
            return {symbol: empty_frame() for symbol in symbols}

        available = set(frame.index.get_level_values("symbol"))
        out: Dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            if symbol not in available:
                out[symbol] = empty_frame()
                continue
            sub = frame.xs(symbol, level="symbol")[OHLCV].copy()
            idx = pd.DatetimeIndex(sub.index)
            sub.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
            out[symbol] = sub.sort_index()
        return out

    def last_prices(self, bars: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        return {
            symbol: float(df["close"].iloc[-1])
            for symbol, df in bars.items()
            if not df.empty
        }
