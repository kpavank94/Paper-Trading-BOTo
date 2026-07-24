"""IBKR implementation of the Broker protocol.

Wraps the existing IBKRInterface rather than replacing it, so the ib_insync
connection handling, order helpers and SQLite logging are preserved. ib_insync
is imported lazily so that Alpaca users do not need it installed.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from ..config import Settings

log = logging.getLogger(__name__)


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
        log.warning(
            "account summary unavailable, falling back to ACCOUNT_EQUITY=%s",
            self.settings.starting_equity,
        )
        return self.settings.starting_equity

    def market_is_open(self) -> bool:
        """IBKR exposes no clock endpoint, so the session gate lives upstream."""
        return True

    def positions(self) -> Dict[str, float]:
        return {p["symbol"]: float(p["quantity"]) for p in self.interface.get_open_positions()}

    def working_symbols(self) -> List[str]:
        try:
            return [t.contract.symbol for t in self.interface.ib.openTrades()]
        except Exception as exc:  # pragma: no cover - depends on live socket
            log.error("could not read open trades: %s", exc)
            return []

    def submit_market_order(
        self, symbol: str, quantity: int, action: str
    ) -> Optional[str]:
        return self.interface.place_market_order(symbol, quantity, action)

    def flatten(self) -> None:
        for symbol, qty in self.positions().items():
            if qty:
                action = "SELL" if qty > 0 else "BUY"
                self.interface.place_market_order(symbol, int(abs(qty)), action)
