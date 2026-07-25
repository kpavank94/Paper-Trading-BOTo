"""Alpaca US-equity daily OHLCV loader (key-gated).

Fetches daily bars from Alpaca's market-data API
(``/v2/stocks/{symbol}/bars``). Free with a paper account; the default IEX feed
needs no paid subscription (override with ``APCA_DATA_FEED=sip`` if entitled).
Credentials: ``APCA_API_KEY_ID`` / ``APCA_API_SECRET_KEY``.

Mirrors the finnhub loader: per-symbol fetch through the opt-in loader cache, a
single failing symbol is logged and skipped, and the returned frame matches the
canonical ``open/high/low/close/volume`` shape on a ``trade_date`` index.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from backtest.loaders._http import resolve_min_interval, throttled_get_json
from backtest.loaders.base import cached_loader_fetch, validate_date_range
from backtest.loaders.registry import register

logger = logging.getLogger(__name__)

_BARS_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
_HOST_KEY = "data.alpaca.markets"
_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _min_interval() -> float:
    """Per-host polite-throttle interval (seconds) for Alpaca data."""
    return resolve_min_interval(_HOST_KEY, default=0.35)


def _to_alpaca_symbol(code: str) -> str:
    """Strip the project ``.US`` suffix Alpaca does not use (``AAPL.US`` -> ``AAPL``)."""
    return code.split(".")[0].upper()


@register
class DataLoader:
    """Alpaca US-equity daily OHLCV loader (key-gated, throttled HTTP)."""

    name = "alpaca"
    markets = {"us_equity"}
    requires_auth = True

    def __init__(self) -> None:
        """Initialize without touching the network or credentials.

        Construction never raises on a missing key; availability is reported
        separately via :meth:`is_available` so the fallback chain keeps walking
        when the key is absent.
        """
        pass

    def is_available(self) -> bool:
        """Return whether Alpaca data credentials are present in the environment."""
        from src.config.accessor import get_env_config

        cfg = get_env_config().data
        return bool(cfg.apca_api_key_id and cfg.apca_api_secret_key)

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch daily OHLCV history keyed by the original project symbols.

        Args:
            codes: Project symbols such as ``AAPL.US`` or ``AAPL``.
            start_date: Inclusive start date in ``YYYY-MM-DD``.
            end_date: Inclusive end date in ``YYYY-MM-DD``.
            interval: Backtest interval; only daily (``1D``) is supported.
            fields: Ignored; present for interface compatibility.

        Returns:
            Mapping of input symbol to a DataFrame indexed by a ``trade_date``
            DatetimeIndex with float OHLCV columns. Symbols without data are omitted.

        Raises:
            ValueError: If ``start_date`` > ``end_date``.
        """
        del fields
        validate_date_range(start_date, end_date)

        from src.config.accessor import get_env_config

        cfg = get_env_config().data
        key_id, secret = cfg.apca_api_key_id, cfg.apca_api_secret_key
        if not (key_id and secret):
            logger.warning("alpaca fetch skipped: APCA_API_KEY_ID / APCA_API_SECRET_KEY not set")
            return {}
        feed = (cfg.apca_data_feed or "iex").strip()

        result: Dict[str, pd.DataFrame] = {}
        for code in codes:
            try:
                df = cached_loader_fetch(
                    source=self.name,
                    symbol=code,
                    timeframe=interval,
                    start_date=start_date,
                    end_date=end_date,
                    fields=None,
                    fetch=lambda code=code: self._fetch_one(
                        code, start_date, end_date, key_id, secret, feed
                    ),
                )
                if df is not None and not df.empty:
                    result[code] = df
            except Exception as exc:  # noqa: BLE001 - one symbol must not abort the batch
                logger.warning("alpaca failed for %s: %s", code, exc)
        return result

    def _fetch_one(
        self, code: str, start_date: str, end_date: str, key_id: str, secret: str, feed: str
    ) -> Optional[pd.DataFrame]:
        """Fetch and normalize one symbol's daily bars, paging until exhausted."""
        headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        url = _BARS_URL.format(symbol=_to_alpaca_symbol(code))

        # Alpaca paginates via next_page_token; follow it so long windows are complete.
        for _ in range(50):  # hard cap: 50 pages * 10k bars covers any daily range
            params: dict[str, Any] = {
                "timeframe": "1Day",
                "start": f"{start_date}T00:00:00Z",
                "end": f"{end_date}T23:59:59Z",
                "adjustment": "all",
                "feed": feed,
                "limit": 10000,
            }
            if page_token:
                params["page_token"] = page_token
            payload = throttled_get_json(
                url, host_key=_HOST_KEY, min_interval=_min_interval(),
                params=params, headers=headers,
            )
            for bar in payload.get("bars") or []:
                rows.append({
                    "trade_date": bar.get("t"),
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "volume": bar.get("v"),
                })
            page_token = payload.get("next_page_token")
            if not page_token:
                break

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"], utc=True).dt.tz_localize(None).astype(
            "datetime64[ns]"
        )
        df = df.set_index("trade_date").sort_index()
        df = df[_OHLCV_COLUMNS].astype(float).dropna(subset=["open", "high", "low", "close"])
        return df
