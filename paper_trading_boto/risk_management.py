"""
Risk management module for Paper Trading BOTo.

This module defines a base class for risk management and a simple
implementation that controls position size and defines stop‑loss /
take‑profit thresholds.  It takes inspiration from open‑source
projects that emphasise position limits, capital preservation and
drawdown protection【362023408974584†L165-L196】.  Users can extend
``RiskManager`` to implement custom sizing rules or more complex
risk controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class RiskManager:
    """Abstract base class for risk management."""

    def determine_position_size(self, base_quantity: int, current_price: float) -> int:
        """Determine how many shares/contracts to trade.

        The default implementation returns ``base_quantity`` unchanged.
        Override this method to implement sizing logic based on
        account value, risk tolerance, volatility, etc.
        """
        return base_quantity

    def should_exit_position(
        self, entry_price: float, current_price: float, position: int
    ) -> bool:
        """Determine whether a position should be closed.

        Default implementation never triggers; override to add stop‑loss
        and take‑profit logic.
        """
        return False


@dataclass
class FixedFractionalRiskManager(RiskManager):
    """Simple risk manager that limits trade size based on a fraction of capital.

    Parameters
    ----------
    max_fraction: float
        Fraction of portfolio value to risk on each trade (e.g., 0.05 for 5 %).
    account_value: float
        Current account equity (can be updated externally).

    The position size is computed as ``max_fraction * account_value / current_price``,
    rounded down to the nearest integer.  This prevents overexposure when prices
    are high or account value is low.
    """

    max_fraction: float = 0.05
    account_value: float = 10000.0

    def determine_position_size(self, base_quantity: int, current_price: float) -> int:
        # Determine maximum affordable quantity given risk fraction
        max_qty = int((self.max_fraction * self.account_value) / current_price)
        # Use the smaller of base_quantity and max_qty
        qty = min(base_quantity, max_qty)
        return max(qty, 0)

    def should_exit_position(
        self, entry_price: float, current_price: float, position: int
    ) -> bool:
        # Example stop‑loss at 10 % loss and take‑profit at 20 % gain
        if position > 0:
            if current_price <= entry_price * 0.9:
                return True
            if current_price >= entry_price * 1.2:
                return True
        return False
