"""IBKR implementation of the Broker protocol.

Wraps the existing IBKRInterface rather than replacing it, so the ib_insync
connection handling, order helpers and SQLite logging are preserved. ib_insync
is imported lazily so that Alpaca users do not need it installed.
"""

from __future__ import annotations

import datetime as dt
import logging
from datetime import time as _time
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from ..config import Settings

log = logging.getLogger(__name__)

_EASTERN = ZoneInfo("America/New_York")


class IBKRBroker:
    def __init__(self, settings: Settings) -> None:
        from ..ibkr_interface import IBKRConnectionParams, IBKRInterface

        self.settings = settings
        self.interface = IBKRInterface(
            params=IBKRConnectionParams(
                host=settings.ibkr.host,
                port=settings.ibkr.port,
                client_id=settings.ibkr.client_id,
                account=settings.ibkr.account,
            ),
            db_path=settings.db_path,
        )

    def connect(self) -> None:
        self.interface.connect()

    def disconnect(self) -> None:
        self.interface.disconnect()

    def equity(self) -> float:
        summary = self.interface.get_account_summary() or {}
        for tag in ("NetLiquidation", "EquityWithLoanValue", "TotalCashValue"):
            if tag in summary:
                return float(summary[tag])
        # Never size orders against a fabricated number. Refusing to trade is the
        # safe failure; falling back to ACCOUNT_EQUITY silently over-leverages a
        # smaller real account.
        raise RuntimeError(
            "IBKR account equity is unavailable; refusing to size orders. Check the "
            "TWS/Gateway connection and, if set, the ACCOUNT number."
        )

    def market_is_open(self, now: Optional[dt.datetime] = None) -> bool:
        """Regular US equity trading hours (Mon-Fri 09:30-16:00 America/New_York).

        IBKR exposes no clock endpoint, so this is a conservative gate. It does
        not know market holidays or half days; on those the exchange simply will
        not fill, but the loop should still not fire around the clock.
        """
        now = (now or dt.datetime.now(_EASTERN)).astimezone(_EASTERN)
        if now.weekday() >= 5:
            return False
        return _time(9, 30) <= now.time() <= _time(16, 0)

    def positions(self) -> Dict[str, float]:
        return {p["symbol"]: float(p["quantity"]) for p in self.interface.get_open_positions()}

    def working_symbols(self) -> List[str]:
        # Propagate failures. An empty list here would silently disable the
        # duplicate-order guard and could resubmit an already-working order.
        return [t.contract.symbol for t in self.interface.ib.openTrades()]

    def submit_market_order(
        self, symbol: str, quantity: int, action: str
    ) -> Optional[str]:
        return self.interface.place_market_order(symbol, quantity, action)

    def flatten(self) -> None:
        for symbol, qty in self.positions().items():
            if qty:
                action = "SELL" if qty > 0 else "BUY"
                self.interface.place_market_order(symbol, int(abs(qty)), action)
