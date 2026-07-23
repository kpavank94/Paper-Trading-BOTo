"""Simulated broker for backtesting.

Execution model:

* Market orders queue until the *next* bar and fill at that bar's open,
  adjusted by ``slippage_bps`` against the trader (paid up on buys,
  received down on sells).  Filling on next-bar-open avoids lookahead
  bias — a signal computed on a bar's close cannot execute at that same
  close.
* Limit orders fill on the first subsequent bar whose range crosses the
  limit price, at the limit price.
* An optional protective stop attached to an entry order becomes a
  standing stop that liquidates the resulting position when a later
  bar's range touches the stop price (filled at the stop, or at the
  bar open if the bar gaps through it).

Commission is a flat per-share amount (IBKR-style default 0.005/share,
min 1.00 per order).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..events import Bar, Fill, OrderRequest, OrderType, Side
from ..portfolio import Portfolio
from .base import Broker


@dataclass
class _OpenOrder:
    order_id: str
    request: OrderRequest


@dataclass
class _StopOrder:
    order_id: str
    symbol: str
    side: Side  # side of the *liquidating* order
    quantity: int
    stop_price: float


class SimulatedBroker(Broker):
    def __init__(
        self,
        initial_cash: float = 100_000.0,
        slippage_bps: float = 1.0,
        commission_per_share: float = 0.005,
        commission_min: float = 1.0,
    ) -> None:
        super().__init__()
        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.slippage_bps = slippage_bps
        self.commission_per_share = commission_per_share
        self.commission_min = commission_min
        self._open_orders: List[_OpenOrder] = []
        self._stop_orders: List[_StopOrder] = []
        self._order_ids = itertools.count(1)
        self._last_prices: Dict[str, float] = {}

    # -- Broker interface -------------------------------------------------

    def submit_order(self, order: OrderRequest) -> Optional[str]:
        order_id = f"sim-{next(self._order_ids)}"
        self._open_orders.append(_OpenOrder(order_id=order_id, request=order))
        return order_id

    def cancel_order(self, order_id: str) -> None:
        self._open_orders = [o for o in self._open_orders if o.order_id != order_id]
        self._stop_orders = [s for s in self._stop_orders if s.order_id != order_id]

    def positions(self) -> Dict[str, int]:
        return {
            symbol: pos.quantity
            for symbol, pos in self.portfolio.positions.items()
            if pos.quantity != 0
        }

    def equity(self) -> float:
        return self.portfolio.equity(self._last_prices)

    # -- Backtest driver hook ---------------------------------------------

    def process_bar(self, bar: Bar) -> None:
        """Advance simulated time by one bar: trigger stops, then fill queued orders."""
        self._last_prices[bar.symbol] = bar.close
        self._trigger_stops(bar)
        pending, self._open_orders = self._open_orders, []
        for open_order in pending:
            if open_order.request.symbol != bar.symbol:
                self._open_orders.append(open_order)
                continue
            fill_price = self._execution_price(open_order.request, bar)
            if fill_price is None:
                self._open_orders.append(open_order)  # limit not reached; stays open
                continue
            self._execute(open_order, fill_price, bar)

    # -- Internals ---------------------------------------------------------

    def _execution_price(self, request: OrderRequest, bar: Bar) -> Optional[float]:
        if request.order_type is OrderType.MARKET:
            slip = bar.open * self.slippage_bps / 10_000.0
            return bar.open + slip if request.side is Side.BUY else bar.open - slip
        # LIMIT: fills at limit price if the bar's range crosses it.
        assert request.limit_price is not None
        if request.side is Side.BUY and bar.low <= request.limit_price:
            return request.limit_price
        if request.side is Side.SELL and bar.high >= request.limit_price:
            return request.limit_price
        return None

    def _commission(self, quantity: int) -> float:
        return max(self.commission_min, quantity * self.commission_per_share)

    def _execute(self, open_order: _OpenOrder, price: float, bar: Bar) -> None:
        request = open_order.request
        fill = Fill(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=price,
            timestamp=bar.timestamp,
            commission=self._commission(request.quantity),
            order_id=open_order.order_id,
        )
        self.portfolio.apply_fill(fill)
        if request.stop_loss_price is not None:
            self._stop_orders.append(
                _StopOrder(
                    order_id=open_order.order_id,
                    symbol=request.symbol,
                    side=Side.SELL if request.side is Side.BUY else Side.BUY,
                    quantity=request.quantity,
                    stop_price=request.stop_loss_price,
                )
            )
        self._emit_fill(fill)

    def _trigger_stops(self, bar: Bar) -> None:
        remaining: List[_StopOrder] = []
        for stop in self._stop_orders:
            if stop.symbol != bar.symbol:
                remaining.append(stop)
                continue
            triggered = (
                bar.low <= stop.stop_price if stop.side is Side.SELL  # long stop
                else bar.high >= stop.stop_price                       # short stop
            )
            if not triggered:
                remaining.append(stop)
                continue
            # Fill at the stop, or at the open if the bar gapped through it.
            if stop.side is Side.SELL:
                price = min(stop.stop_price, bar.open)
            else:
                price = max(stop.stop_price, bar.open)
            fill = Fill(
                symbol=stop.symbol,
                side=stop.side,
                quantity=stop.quantity,
                price=price,
                timestamp=bar.timestamp,
                commission=self._commission(stop.quantity),
                order_id=f"{stop.order_id}-stop",
            )
            self.portfolio.apply_fill(fill)
            self._emit_fill(fill)
        self._stop_orders = remaining
