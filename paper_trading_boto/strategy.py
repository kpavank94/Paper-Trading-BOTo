"""
Strategy definitions and base classes for Paper Trading BOTo.

This module defines abstract classes for trading strategies and
implements a sample moving average crossover strategy.  Each strategy
interacts with the IBKR API via the ``IBKRInterface`` and may use
optional risk management and cost basis components.  Strategies are
responsible for deciding when to buy or sell and for managing their
internal state (e.g., whether a position is open).

Key design principles drawn from other projects include:

* **Separation of concerns:**  Strategy logic should be separate from
  connectivity.  The ``trading‑bot‑framework`` emphasises modular
  strategy development and a clean architecture【305661766794282†L175-L197】.
* **Extensibility:**  Users should be able to implement custom
  strategies by subclassing ``BaseStrategy``.  Only a few methods
  need to be overridden.
* **Risk awareness:**  Strategies must incorporate risk management;
  thus each tick delegates to a ``RiskManager`` to determine
  position size and stop levels【362023408974584†L165-L196】.
"""

from __future__ import annotations

import datetime
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .ibkr_interface import IBKRInterface
from .risk_management import RiskManager
from .cost_basis import CostBasisTracker, TradeRecord


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(
        self,
        ibkr: IBKRInterface,
        symbol: str,
        quantity: int,
        risk_manager: RiskManager,
        cost_tracker: CostBasisTracker,
    ) -> None:
        self.ibkr = ibkr
        self.symbol = symbol
        self.quantity = quantity
        self.risk_manager = risk_manager
        self.cost_tracker = cost_tracker
        self.logger = self.ibkr.logger.getChild(self.__class__.__name__)
        self.position = 0  # positive for long, negative for short
        self.entry_price: Optional[float] = None
        self.last_tick_time: Optional[datetime.datetime] = None

    @abstractmethod
    def on_start(self) -> None:
        """Called once before the trading loop begins."""

    @abstractmethod
    def on_tick(self, price: float, timestamp: datetime.datetime) -> None:
        """Called at each iteration with the latest market price."""

    def on_finish(self) -> None:
        """Called once after the trading loop finishes."""
        self.logger.info("Strategy finished trading session")


@dataclass
class SMACrossoverStrategy(BaseStrategy):
    """Simple moving average (SMA) crossover strategy.

    This example strategy maintains two moving averages (short and
    long) and enters a long position when the short MA crosses above
    the long MA.  It exits (sells) when the short MA crosses below
    the long MA.  Only one position is held at a time.  Position
    size is determined by the provided ``RiskManager``.
    """

    ibkr: IBKRInterface
    symbol: str
    quantity: int
    risk_manager: RiskManager
    cost_tracker: CostBasisTracker
    short_window: int = 10
    long_window: int = 30
    prices: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(self.ibkr, self.symbol, self.quantity, self.risk_manager, self.cost_tracker)
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be less than long_window")
        self.logger.info(
            f"Initialised SMA crossover strategy for {self.symbol} with short={self.short_window}, long={self.long_window}"
        )

    def on_start(self) -> None:
        self.logger.info(f"Starting SMA crossover strategy for {self.symbol}")

    def on_tick(self, price: float, timestamp: datetime.datetime) -> None:
        self.last_tick_time = timestamp
        # Append latest price
        self.prices.append(price)
        # Keep only required window of prices
        max_len = self.long_window + 1
        if len(self.prices) > max_len:
            self.prices = self.prices[-max_len:]

        # We need at least 'long_window' observations
        if len(self.prices) < self.long_window:
            return

        short_ma = np.mean(self.prices[-self.short_window :])
        long_ma = np.mean(self.prices[-self.long_window :])
        self.logger.debug(
            f"Price={price:.2f}, short_ma={short_ma:.2f}, long_ma={long_ma:.2f}, position={self.position}"
        )

        # Generate signals
        if self.position <= 0 and short_ma > long_ma:
            # Signal to go long
            qty = self.risk_manager.determine_position_size(self.quantity, price)
            order_id = self.ibkr.place_market_order(self.symbol, qty, "BUY")
            if order_id:
                self.position += qty
                self.entry_price = price
                self.cost_tracker.record_trade(
                    TradeRecord(
                        symbol=self.symbol,
                        action="BUY",
                        quantity=qty,
                        price=price,
                        timestamp=timestamp,
                    )
                )
                self.logger.info(f"Entered long position: {qty} shares at {price:.2f}")

        elif self.position > 0 and short_ma < long_ma:
            # Exit long position
            qty = abs(self.position)
            order_id = self.ibkr.place_market_order(self.symbol, qty, "SELL")
            if order_id:
                self.position = 0
                self.entry_price = None
                self.cost_tracker.record_trade(
                    TradeRecord(
                        symbol=self.symbol,
                        action="SELL",
                        quantity=qty,
                        price=price,
                        timestamp=timestamp,
                    )
                )
                self.logger.info(f"Exited long position: {qty} shares at {price:.2f}")
