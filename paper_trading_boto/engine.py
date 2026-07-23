"""Event loop connecting a DataFeed, Strategy, RiskManager and Broker.

The engine is broker- and feed-agnostic: the backtest runner wires it to
a YFinanceFeed + SimulatedBroker, the live runner to an IBKR feed +
IBKRBroker.  Responsibilities:

* feed warmup history to the strategy before the first live bar
* per bar: let the strategy signal, size it through the risk layer,
  submit the order
* mirror broker fills into the local Portfolio (fills are the only
  source of position truth)
* run the risk backstop exit check with the bar close (never a missing
  price) and honor the drawdown kill-switch
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .broker.base import Broker
from .data.base import DataFeed
from .events import Bar, Fill, OrderRequest, Side
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class Engine:
    feed: DataFeed
    strategy: Strategy
    risk: RiskManager
    broker: Broker
    portfolio: Portfolio = field(default_factory=Portfolio)
    # Optional observer invoked after each processed bar (used by the
    # backtest runner to sample the equity curve).
    on_bar_end: Optional[Callable[[Bar], None]] = None

    def __post_init__(self) -> None:
        self._last_prices: Dict[str, float] = {}
        self._entry_price: Optional[float] = None
        self._stopping = False
        self.broker.on_fill(self._handle_fill)

    # -- Fill handling -------------------------------------------------------

    def _handle_fill(self, fill: Fill) -> None:
        self.portfolio.apply_fill(fill)
        if fill.side is Side.BUY and self.portfolio.quantity(fill.symbol) > 0:
            self._entry_price = fill.price
        elif self.portfolio.quantity(fill.symbol) == 0:
            self._entry_price = None
        logger.info(
            "FILL %s %s %d @ %.2f (commission %.2f)",
            fill.side.value, fill.symbol, fill.quantity, fill.price, fill.commission,
        )

    # -- Main loop -------------------------------------------------------------

    def stop(self) -> None:
        self._stopping = True
        self.feed.stop()

    def run(self) -> Portfolio:
        history = self.feed.warmup(self.strategy.warmup_bars())
        self.strategy.on_start(history)
        logger.info(
            "Engine start: %s, %d warmup bars", type(self.strategy).__name__, len(history)
        )
        try:
            for bar in self.feed.bars():
                if self._stopping:
                    break
                self._process_bar(bar)
                if self.on_bar_end is not None:
                    self.on_bar_end(bar)
        finally:
            self.strategy.on_finish()
        return self.portfolio

    def _process_bar(self, bar: Bar) -> None:
        self._last_prices[bar.symbol] = bar.close

        # Let a simulated broker advance (fills queued orders, triggers stops).
        process_bar = getattr(self.broker, "process_bar", None)
        if process_bar is not None:
            process_bar(bar)

        equity = self.broker.equity()
        self.risk.update_equity(equity)
        if self.risk.halted:
            self._flatten(bar, reason="max drawdown kill-switch")
            return

        position = self.portfolio.quantity(bar.symbol)

        # Backstop exit: broker-side stop should fire first, but if the
        # engine sees the level crossed on the close, exit here too.
        if position > 0 and self._entry_price is not None and self.risk.should_exit(
            self._entry_price, bar.close, position
        ):
            self._submit(OrderRequest(symbol=bar.symbol, side=Side.SELL, quantity=position))
            return

        signal = self.strategy.on_bar(bar)
        if signal is None:
            return
        exposure = abs(position) * bar.close
        order = self.risk.order_for_signal(
            signal, price=bar.close, equity=equity,
            current_position=position, current_exposure=exposure,
        )
        if order is not None:
            logger.info("SIGNAL %s -> %s %d %s", signal.reason, order.side.value,
                        order.quantity, order.symbol)
            self._submit(order)

    def _flatten(self, bar: Bar, reason: str) -> None:
        position = self.portfolio.quantity(bar.symbol)
        if position > 0:
            logger.warning("Flattening %s (%s)", bar.symbol, reason)
            self._submit(OrderRequest(symbol=bar.symbol, side=Side.SELL, quantity=position))

    def _submit(self, order: OrderRequest) -> None:
        order_id = self.broker.submit_order(order)
        if order_id is None:
            logger.error("Order rejected: %s %d %s", order.side.value, order.quantity,
                         order.symbol)
