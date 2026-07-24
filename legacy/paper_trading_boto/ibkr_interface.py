"""
Interface layer for connecting to the Interactive Brokers (IBKR) API
using the ``ib_insync`` library.

This module encapsulates the setup and basic operations required to
interact with IBKR in a paper trading environment.  The
``IBKRInterface`` class manages the connection lifecycle, requests
market data, submits orders and queries account information.  It
leverages ``ib_insync`` to provide a synchronous API on top of the
official ``ibapi`` client, simplifying asynchronous event handling and
error management【730412866638135†L82-L90】.

The code here is deliberately simple to illustrate how one might build
a thin wrapper around ``ib_insync``.  For a production‑grade system you
should add more robust error handling, reconnection logic and rate
limiting, as suggested in open‑source trading bots【259634449855701†L83-L92】.

Note:  This module does not perform any strategy logic—that is handled
by classes in ``strategy.py``.  Instead it focuses on connectivity and
order execution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Union

try:
    from ib_insync import IB, util, Contract, Stock, MarketOrder, LimitOrder
except ImportError:
    raise ImportError(
        "The ib_insync package is required.  Install it via 'pip install ib_insync'."
    )

from .utils.logging_config import configure_logging


@dataclass
class IBKRConnectionParams:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    account: Optional[str] = None


class IBKRInterface:
    """High‑level interface for connecting to IBKR via ib_insync."""

    def __init__(self, params: IBKRConnectionParams, db_path: Optional[str] = None) -> None:
        self.params = params
        # Configure logger; DB logging uses the provided db_path
        self.logger = configure_logging(name="ibkr_interface", db_path=db_path)
        self.ib = IB()

    def connect(self) -> None:
        """Establish a connection to TWS or IB Gateway."""
        self.logger.info(
            f"Connecting to IBKR host={self.params.host}, port={self.params.port}, client_id={self.params.client_id}"
        )
        self.ib.connect(
            host=self.params.host,
            port=self.params.port,
            clientId=self.params.client_id,
        )
        if self.params.account:
            # Ensure account is valid; fetch account summary
            summary = self.get_account_summary()
            if not summary:
                self.logger.warning(
                    f"Account '{self.params.account}' could not be verified.  Proceeding without explicit account."
                )
        self.logger.info("Connected to IBKR API")

    def disconnect(self) -> None:
        """Disconnect from IBKR."""
        if self.ib.isConnected():
            self.logger.info("Disconnecting from IBKR...")
            self.ib.disconnect()

    def get_account_summary(self) -> Optional[dict]:
        """Return a dictionary of account summary values for the specified account (if available)."""
        if not self.params.account:
            return None
        try:
            summary_list = self.ib.accountSummary()
            summary = {item.tag: item.value for item in summary_list if item.account == self.params.account}
            return summary
        except Exception as exc:
            self.logger.error(f"Failed to fetch account summary: {exc}")
            return None

    # Market data
    def get_current_price(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Optional[float]:
        """Fetch the latest price for a given symbol.

        Parameters
        ----------
        symbol: str
            Ticker symbol (e.g., 'AAPL').
        exchange: str
            Primary exchange (defaults to 'SMART' for IBKR).  Use 'NASDAQ', 'NYSE', etc.
        currency: str
            Currency of the instrument (default 'USD').

        Returns
        -------
        Optional[float]
            The last traded price if available, otherwise ``None``.
        """
        contract = Stock(symbol, exchange, currency)
        try:
            ticker = self.ib.reqMktData(contract, snapshot=True)
            # Wait for tick data (synchronous thanks to ib_insync)
            self.ib.sleep(1)
            price = ticker.last
            if price is None:
                price = ticker.close
            return float(price) if price is not None else None
        except Exception as exc:
            self.logger.error(f"Failed to fetch market data for {symbol}: {exc}")
            return None

    def place_market_order(
        self,
        symbol: str,
        quantity: int,
        action: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> Optional[str]:
        """Submit a simple market order.

        Parameters
        ----------
        symbol: str
            Instrument symbol.
        quantity: int
            Number of shares/contracts to buy (positive) or sell (positive).  Action determines buy/sell.
        action: str
            Either 'BUY' or 'SELL'.
        exchange: str, optional
            Exchange route (default 'SMART').
        currency: str, optional
            Currency (default 'USD').

        Returns
        -------
        Optional[str]
            Order ID if successfully submitted; otherwise ``None``.
        """
        if action.upper() not in {"BUY", "SELL"}:
            raise ValueError("action must be 'BUY' or 'SELL'")
        contract = Stock(symbol, exchange, currency)
        order = MarketOrder(action.upper(), quantity)
        try:
            trade = self.ib.placeOrder(contract, order)
            self.logger.info(f"Placed market order {trade.order.orderId}: {action} {quantity} {symbol}")
            return str(trade.order.orderId)
        except Exception as exc:
            self.logger.error(f"Failed to place market order: {exc}")
            return None

    def place_limit_order(
        self,
        symbol: str,
        quantity: int,
        action: str,
        limit_price: float,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> Optional[str]:
        """Submit a limit order.

        Parameters
        ----------
        symbol: str
            Symbol to trade.
        quantity: int
            Quantity to buy or sell.
        action: str
            'BUY' or 'SELL'.
        limit_price: float
            Price at which to place the limit order.
        exchange: str, optional
            Exchange for routing.
        currency: str, optional
            Currency.
        """
        if action.upper() not in {"BUY", "SELL"}:
            raise ValueError("action must be 'BUY' or 'SELL'")
        contract = Stock(symbol, exchange, currency)
        order = LimitOrder(action.upper(), quantity, limit_price)
        try:
            trade = self.ib.placeOrder(contract, order)
            self.logger.info(
                f"Placed limit order {trade.order.orderId}: {action} {quantity} {symbol} at {limit_price}"
            )
            return str(trade.order.orderId)
        except Exception as exc:
            self.logger.error(f"Failed to place limit order: {exc}")
            return None

    def cancel_order(self, order_id: Union[str, int]) -> None:
        """Cancel an active order by ID."""
        try:
            open_orders = self.ib.openTrades()
            for trade in open_orders:
                if str(trade.order.orderId) == str(order_id):
                    self.ib.cancelOrder(trade.order)
                    self.logger.info(f"Cancelled order {order_id}")
                    return
            self.logger.warning(f"Order {order_id} not found among open trades.")
        except Exception as exc:
            self.logger.error(f"Failed to cancel order {order_id}: {exc}")

    def get_open_positions(self) -> List[dict]:
        """Return a list of open positions with quantity and cost basis."""
        positions = []
        try:
            ib_positions = self.ib.positions()
            for pos in ib_positions:
                positions.append(
                    {
                        "symbol": pos.contract.symbol,
                        "quantity": pos.position,
                        "avgCost": pos.avgCost,
                    }
                )
            return positions
        except Exception as exc:
            self.logger.error(f"Failed to fetch positions: {exc}")
            return positions

    def get_trade_history(self) -> List[dict]:
        """Retrieve recent trades (fills)."""
        try:
            fills = self.ib.fills()
            trades = []
            for fill in fills:
                trades.append(
                    {
                        "orderId": fill.contract.conId,
                        "symbol": fill.contract.symbol,
                        "action": fill.execution.side,
                        "quantity": fill.execution.shares,
                        "price": fill.execution.price,
                        "time": fill.execution.time,
                    }
                )
            return trades
        except Exception as exc:
            self.logger.error(f"Failed to fetch trade history: {exc}")
            return []