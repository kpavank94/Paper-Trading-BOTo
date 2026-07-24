"""Risk management for Paper Trading BOTo.

The original module sized trades as a flat fraction of capital and exited on
fixed percentage moves, which applies the same stop distance to a utility and
to a small cap regardless of how much either one actually moves. Sizing is now
volatility aware and lives in the strategy, while this module owns the
portfolio level guards that must hold no matter what the signal says:

* a gross exposure ceiling;
* a per symbol weight ceiling;
* a drawdown kill switch that flattens the book and stops new entries.

The legacy RiskManager and FixedFractionalRiskManager classes are retained so
existing custom subclasses keep working.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RiskManager:
    """Legacy per trade interface. Prefer PortfolioRiskManager for new code."""

    def determine_position_size(self, base_quantity: int, current_price: float) -> int:
        return base_quantity

    def should_exit_position(
        self, entry_price: float, current_price: float, position: int
    ) -> bool:
        return False


@dataclass
class FixedFractionalRiskManager(RiskManager):
    """Caps trade size at a fixed fraction of account value."""

    max_fraction: float = 0.05
    account_value: float = 10000.0
    stop_loss_pct: float = 0.10
    take_profit_pct: float = 0.20

    def determine_position_size(self, base_quantity: int, current_price: float) -> int:
        if current_price <= 0:
            return 0
        max_qty = int((self.max_fraction * self.account_value) / current_price)
        return max(min(base_quantity, max_qty), 0)

    def should_exit_position(
        self, entry_price: float, current_price: float, position: int
    ) -> bool:
        if position > 0 and entry_price > 0:
            if current_price <= entry_price * (1.0 - self.stop_loss_pct):
                return True
            if current_price >= entry_price * (1.0 + self.take_profit_pct):
                return True
        return False


@dataclass
class PortfolioRiskManager:
    """Portfolio level constraints applied after the strategy proposes weights.

    Parameters
    ----------
    max_gross_exposure:
        Ceiling on the sum of absolute weights.
    max_weight:
        Ceiling on any single symbol's weight.
    max_drawdown_stop:
        Fraction of peak equity that, once lost, halts new entries. The peak is
        tracked across calls to ``update_equity``.
    """

    max_gross_exposure: float = 1.0
    max_weight: float = 0.5
    max_drawdown_stop: float = 0.20
    peak_equity: float = 0.0
    halted: bool = False
    state_path: Optional[str] = None
    last_equity: float = 0.0
    _history: list = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        # Persisted so the kill switch and its high-water mark survive a process
        # restart. Without this, peak_equity re-seeds to the current (drawn-down)
        # equity on every run and a halt silently clears itself.
        self._load()

    def _load(self) -> None:
        if not self.state_path:
            return
        try:
            with open(self.state_path) as fh:
                state = json.load(fh)
        except (OSError, ValueError):
            return
        self.peak_equity = max(self.peak_equity, float(state.get("peak_equity", 0.0)))
        self.halted = self.halted or bool(state.get("halted", False))
        self.last_equity = float(state.get("last_equity", self.last_equity))

    def _save(self) -> None:
        if not self.state_path:
            return
        try:
            with open(self.state_path, "w") as fh:
                json.dump(
                    {
                        "peak_equity": self.peak_equity,
                        "halted": self.halted,
                        "last_equity": self.last_equity,
                    },
                    fh,
                )
        except OSError as exc:
            logger.warning("could not persist risk state to %s: %s", self.state_path, exc)

    def update_equity(self, equity: float) -> bool:
        """Record equity and return True if trading should be halted."""
        self._history.append(equity)
        self.last_equity = equity
        self.peak_equity = max(self.peak_equity, equity)
        if self.peak_equity > 0:
            drawdown = 1.0 - equity / self.peak_equity
            if drawdown >= self.max_drawdown_stop:
                self.halted = True
        self._save()
        return self.halted

    @property
    def drawdown(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return 1.0 - self.last_equity / self.peak_equity

    def apply(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Clamp per symbol weights, then scale down to the gross ceiling."""
        if self.halted:
            return {symbol: 0.0 for symbol in weights}

        clamped = {
            symbol: max(min(weight, self.max_weight), -self.max_weight)
            for symbol, weight in weights.items()
        }
        gross = sum(abs(w) for w in clamped.values())
        if gross > self.max_gross_exposure and gross > 0:
            scale = self.max_gross_exposure / gross
            clamped = {symbol: w * scale for symbol, w in clamped.items()}
        return clamped

    def reset(self, equity: Optional[float] = None) -> None:
        self.halted = False
        self._history = []
        self.peak_equity = equity or 0.0
        self.last_equity = equity or 0.0
        self._save()
