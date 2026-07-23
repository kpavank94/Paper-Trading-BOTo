"""IBKR broker adapter over ib_async (successor to the archived ib_insync).

Fixes relative to the original ``ibkr_interface.py``:

* **Fill confirmation**: positions update from ``fillEvent`` callbacks,
  never optimistically at submission time.
* **NaN safety**: ib_async reports unknown prices as ``nan`` — the old
  ``price is not None`` check let NaN through into the SMAs.  All prices
  pass through :func:`_clean_price`.
* **Reconciliation**: on connect, existing broker positions are exposed
  so a restarted bot does not double-enter or orphan a position.
* **Broker-side stops**: entries with a stop attach a real STP order via
  a bracket, so protection survives the bot process dying.
* **Ticker hygiene**: no snapshot-per-poll leak; market data requests
  are cancelled when no longer needed.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Dict, Optional

from ib_async import IB, LimitOrder, MarketOrder, Stock, StopOrder, Trade
from ib_async import Fill as IBFill

from ..events import Fill, OrderRequest, OrderType, Side, utcnow
from .base import Broker

logger = logging.getLogger(__name__)


def _clean_price(value: Optional[float]) -> Optional[float]:
    """Return a finite positive price or None (ib_async uses nan for unknown)."""
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    return price


class IBKRBroker(Broker):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        account: Optional[str] = None,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> None:
        super().__init__()
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.exchange = exchange
        self.currency = currency
        self._seen_fills: set = set()
        self._lock = threading.Lock()

    # -- Lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        logger.info("Connecting to IBKR %s:%s (client id %s)", self.host, self.port,
                    self.client_id)
        self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
        self.ib.fillEvent += self._on_ib_fill
        reconciled = self.positions()
        if reconciled:
            logger.warning("Existing broker positions at startup: %s", reconciled)

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.fillEvent -= self._on_ib_fill
            self.ib.disconnect()

    def _contract(self, symbol: str) -> Stock:
        return Stock(symbol, self.exchange, self.currency)

    # -- Fill plumbing ---------------------------------------------------------

    def _on_ib_fill(self, trade: Trade, fill: IBFill) -> None:
        """Translate an ib_async fill event into our Fill exactly once."""
        exec_id = fill.execution.execId
        with self._lock:
            if exec_id in self._seen_fills:
                return
            self._seen_fills.add(exec_id)
        commission = 0.0
        if fill.commissionReport and math.isfinite(fill.commissionReport.commission or math.nan):
            commission = float(fill.commissionReport.commission)
        side = Side.BUY if fill.execution.side.upper().startswith("B") else Side.SELL
        our_fill = Fill(
            symbol=fill.contract.symbol,
            side=side,
            quantity=int(fill.execution.shares),
            price=float(fill.execution.price),
            timestamp=fill.time or utcnow(),
            commission=commission,
            order_id=str(trade.order.orderId),
        )
        logger.info("IBKR fill: %s %s %d @ %.2f", our_fill.side.value, our_fill.symbol,
                    our_fill.quantity, our_fill.price)
        self._emit_fill(our_fill)

    # -- Broker interface ---------------------------------------------------------

    def submit_order(self, order: OrderRequest) -> Optional[str]:
        contract = self._contract(order.symbol)
        try:
            if order.order_type is OrderType.LIMIT:
                ib_order = LimitOrder(order.side.value, order.quantity, order.limit_price)
            else:
                ib_order = MarketOrder(order.side.value, order.quantity)
            if order.stop_loss_price is not None:
                # Parent + protective stop transmitted atomically.
                ib_order.transmit = False
                parent_trade = self.ib.placeOrder(contract, ib_order)
                stop_side = "SELL" if order.side is Side.BUY else "BUY"
                stop = StopOrder(stop_side, order.quantity, order.stop_loss_price)
                stop.parentId = parent_trade.order.orderId
                stop.transmit = True
                self.ib.placeOrder(contract, stop)
                trade = parent_trade
            else:
                trade = self.ib.placeOrder(contract, ib_order)
            logger.info("Submitted %s %d %s (order id %s)", order.side.value,
                        order.quantity, order.symbol, trade.order.orderId)
            return str(trade.order.orderId)
        except Exception:
            logger.exception("Order submission failed: %s %d %s", order.side.value,
                             order.quantity, order.symbol)
            return None

    def cancel_order(self, order_id: str) -> None:
        for trade in self.ib.openTrades():
            if str(trade.order.orderId) == str(order_id):
                self.ib.cancelOrder(trade.order)
                logger.info("Cancelled order %s", order_id)
                return
        logger.warning("Order %s not found among open trades", order_id)

    def positions(self) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for pos in self.ib.positions(account=self.account or ""):
            if pos.position:
                result[pos.contract.symbol] = int(pos.position)
        return result

    def equity(self) -> float:
        """Net liquidation value from the account summary."""
        for row in self.ib.accountSummary(account=self.account or ""):
            if row.tag == "NetLiquidation":
                value = _clean_price(row.value)
                if value is not None:
                    return value
        logger.warning("NetLiquidation unavailable; returning 0.0")
        return 0.0

    # -- Market data helper (used by the live feed and webhook) -----------------

    def current_price(self, symbol: str) -> Optional[float]:
        """Delayed-safe last/close price, NaN-cleaned, ticker cancelled after."""
        contract = self._contract(symbol)
        ticker = self.ib.reqMktData(contract, "", snapshot=True)
        try:
            self.ib.sleep(2.0)
            return _clean_price(ticker.last) or _clean_price(ticker.close)
        finally:
            self.ib.cancelMktData(contract)
