"""Broker abstraction shared by the Alpaca and IBKR implementations.

Strategy code targets portfolio weights and never talks to a broker SDK
directly, so the same signals can be routed to either venue or to the
backtester without modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Intent:
    """A share delta that has passed sizing and minimum notional checks."""

    symbol: str
    delta_shares: int
    notional: float

    @property
    def action(self) -> str:
        return "BUY" if self.delta_shares > 0 else "SELL"

    @property
    def quantity(self) -> int:
        return abs(self.delta_shares)


@runtime_checkable
class Broker(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def equity(self) -> float: ...

    def market_is_open(self) -> bool: ...

    def positions(self) -> Dict[str, float]: ...

    def working_symbols(self) -> List[str]: ...

    def submit_market_order(self, symbol: str, quantity: int, action: str) -> Optional[str]: ...

    def flatten(self) -> None: ...


def plan_orders(
    target_weights: Dict[str, float],
    prices: Dict[str, float],
    equity: float,
    held: Dict[str, float],
    min_notional: float = 50.0,
    blocked: Optional[set] = None,
) -> List[Intent]:
    """Difference target weights against the live book.

    Pure function with no network calls, which is what makes the reconciliation
    rules testable. Symbols held but no longer targeted are closed.
    """
    blocked = blocked or set()
    intents: List[Intent] = []

    for symbol in sorted(set(target_weights) | set(held)):
        if symbol in blocked:
            continue
        held_qty = held.get(symbol, 0.0)
        target_weight = target_weights.get(symbol, 0.0)
        price = prices.get(symbol)

        if not price or price <= 0:
            # Without a price we cannot size a position, but a holding that is no
            # longer targeted must still be closed. Emit the full liquidation with
            # an unknown notional rather than silently stranding the position.
            if target_weight == 0.0 and held_qty != 0:
                intents.append(
                    Intent(symbol=symbol, delta_shares=int(-held_qty), notional=0.0)
                )
            continue

        # int() truncates toward zero for both signs; math.floor() rounds a short
        # target away from zero and would oversize it.
        desired = int(target_weight * equity / price)
        delta = int(desired - held_qty)
        if delta == 0:
            continue
        notional = abs(delta) * price
        # The minimum-notional filter suppresses tiny rebalancing adjustments, but
        # it must never block a full exit, or a small leftover holding can never
        # be closed.
        closing = desired == 0
        if notional < min_notional and not closing:
            continue
        intents.append(Intent(symbol=symbol, delta_shares=delta, notional=notional))
    return intents
