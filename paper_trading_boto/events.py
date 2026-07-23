"""Core event types shared by the engine, brokers, data feeds and strategies.

Everything that flows through the system is one of these immutable
dataclasses.  Strategies consume :class:`Bar` and emit :class:`Signal`;
the engine converts signals into :class:`OrderRequest` via the risk
layer; brokers report executions back as :class:`Fill`.  Positions are
derived from fills only — never from orders that were merely submitted.
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field
from typing import Optional


class Side(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class SignalAction(str, enum.Enum):
    """What a strategy wants to do with its position in one symbol."""

    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_SHORT = "EXIT_SHORT"


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar. ``timestamp`` is the bar *open* time, timezone-aware UTC."""

    symbol: str
    timestamp: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Bar.timestamp must be timezone-aware")


@dataclass(frozen=True)
class Signal:
    """Strategy intent. Sizing is decided by the risk layer, not the strategy."""

    symbol: str
    action: SignalAction
    timestamp: dt.datetime
    reason: str = ""


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    # Broker-side protective stop attached on entry (None = no stop).
    stop_loss_price: Optional[float] = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("OrderRequest.quantity must be positive")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price required for LIMIT orders")


@dataclass(frozen=True)
class Fill:
    """A confirmed execution reported by a broker."""

    symbol: str
    side: Side
    quantity: int
    price: float
    timestamp: dt.datetime
    commission: float = 0.0
    order_id: str = ""


def utcnow() -> dt.datetime:
    """Timezone-aware replacement for the deprecated ``datetime.utcnow()``."""
    return dt.datetime.now(dt.timezone.utc)
