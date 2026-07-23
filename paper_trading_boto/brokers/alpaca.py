"""Alpaca implementation of the Broker protocol.

Verified against alpaca-py 0.43.x: TradingClient.get_account, get_clock,
get_all_positions, get_orders(filter=...), submit_order(order_data=...) and
close_all_positions(cancel_orders=...).
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from ..config import Settings

log = logging.getLogger(__name__)


class AlpacaBroker:
    def __init__(self, settings: Settings) -> None:
        creds = settings.require_alpaca()
        self.settings = settings
        self.client = TradingClient(
            creds.api_key, creds.secret_key, paper=creds.paper
        )

    def connect(self) -> None:
        account = self.client.get_account()
        log.info(
            "connected to alpaca account %s (paper=%s) equity=%s",
            account.account_number,
            self.settings.alpaca.paper,
            account.equity,
        )

    def disconnect(self) -> None:
        return None

    def equity(self) -> float:
        return float(self.client.get_account().equity)

    def market_is_open(self) -> bool:
        return bool(self.client.get_clock().is_open)

    def positions(self) -> Dict[str, float]:
        return {p.symbol: float(p.qty) for p in self.client.get_all_positions()}

    def working_symbols(self) -> List[str]:
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        return [order.symbol for order in self.client.get_orders(filter=request)]

    def submit_market_order(
        self, symbol: str, quantity: int, action: str
    ) -> Optional[str]:
        if action.upper() not in {"BUY", "SELL"}:
            raise ValueError("action must be 'BUY' or 'SELL'")
        request = MarketOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=OrderSide.BUY if action.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=f"{self.settings.client_order_prefix}-{uuid.uuid4().hex[:16]}",
        )
        try:
            order = self.client.submit_order(order_data=request)
            log.info("submitted %s %s %s id=%s", action, quantity, symbol, order.id)
            return str(order.id)
        except APIError as exc:
            log.error("order rejected for %s: %s", symbol, exc)
            return None

    def flatten(self) -> None:
        self.client.close_all_positions(cancel_orders=True)
