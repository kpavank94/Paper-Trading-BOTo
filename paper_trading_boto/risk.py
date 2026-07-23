"""Risk management: sizing, protective stops and a drawdown kill-switch.

Port of ``risk_management.py`` with the failure modes fixed:

* Sizing uses *current* broker equity, queried per trade — the old
  manager froze ``account_value`` at construction time.
* The stop-loss is attached to the entry order and lives broker-side
  (``OrderRequest.stop_loss_price``); it does not depend on the bot's
  poll loop staying alive.
* ``should_exit`` treats a missing price as "no information" and never
  triggers.  The original bot passed ``price or 0.0`` into the check, so
  a single failed market-data fetch liquidated any long position.
* A max-drawdown kill-switch halts all new entries for the session.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .events import OrderRequest, OrderType, Side, Signal, SignalAction


@dataclass
class RiskManager:
    risk_fraction: float = 0.05       # max fraction of equity per position
    max_portfolio_exposure: float = 0.2
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    max_drawdown_pct: float = 0.25

    def __post_init__(self) -> None:
        self._peak_equity: Optional[float] = None
        self.halted = False

    # -- Kill-switch --------------------------------------------------------

    def update_equity(self, equity: float) -> None:
        """Track peak equity; halt new entries past the max-drawdown limit."""
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity
        elif self._peak_equity > 0:
            drawdown = 1.0 - equity / self._peak_equity
            if drawdown >= self.max_drawdown_pct and not self.halted:
                self.halted = True

    # -- Order construction --------------------------------------------------

    def order_for_signal(
        self,
        signal: Signal,
        price: float,
        equity: float,
        current_position: int,
        current_exposure: float = 0.0,
    ) -> Optional[OrderRequest]:
        """Turn a strategy signal into a sized order, or None if disallowed.

        ``current_exposure`` is the market value of all open positions
        excluding cash, used to enforce ``max_portfolio_exposure``.
        """
        if price is None or not math.isfinite(price) or price <= 0:
            return None

        if signal.action is SignalAction.ENTER_LONG:
            if self.halted or current_position > 0:
                return None
            budget = self.risk_fraction * equity
            headroom = self.max_portfolio_exposure * equity - current_exposure
            quantity = int(min(budget, max(headroom, 0.0)) / price)
            if quantity <= 0:
                return None
            return OrderRequest(
                symbol=signal.symbol,
                side=Side.BUY,
                quantity=quantity,
                order_type=OrderType.MARKET,
                stop_loss_price=round(price * (1.0 - self.stop_loss_pct), 2),
            )

        if signal.action is SignalAction.EXIT_LONG:
            if current_position <= 0:
                return None
            return OrderRequest(
                symbol=signal.symbol, side=Side.SELL, quantity=current_position
            )

        # Short entries/exits intentionally unsupported for now: the sample
        # strategy is long-only and shorting needs margin-aware sizing.
        return None

    # -- Position exit checks --------------------------------------------------

    def should_exit(
        self, entry_price: float, current_price: Optional[float], position: int
    ) -> bool:
        """Take-profit / stop-loss check on a marked price.

        A missing or non-finite price is NO information and never
        triggers an exit (regression guard for the ``price or 0.0`` bug).
        The stop side is normally handled broker-side; this is a backstop
        used by the engine between fills.
        """
        if current_price is None or not math.isfinite(current_price):
            return False
        if position > 0:
            if current_price <= entry_price * (1.0 - self.stop_loss_pct):
                return True
            if current_price >= entry_price * (1.0 + self.take_profit_pct):
                return True
        return False
