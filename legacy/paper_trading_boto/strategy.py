"""Strategy definitions for Paper Trading BOTo.

Strategies now consume a DataFrame of OHLCV bars and emit a *target weight*
per bar: the fraction of account equity the book should hold in that symbol.
This replaces the previous design where the strategy called the broker
directly from inside on_tick.

Two properties follow from the change:

* the identical code path drives the backtester and the live runner, so a
  backtest actually tests what will be traded;
* every column is computable from information available at or before the
  bar's close. The one bar execution lag is applied by the backtester and the
  runner, never inside the signal, which is what keeps the results honest.

Subclass BaseStrategy and implement evaluate() to add your own logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd


def wilder_atr(df: pd.DataFrame, window: int) -> pd.Series:
    """Average true range using Wilder's smoothing."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


class BaseStrategy(ABC):
    """Abstract base class for bar driven strategies."""

    @property
    @abstractmethod
    def warmup(self) -> int:
        """Bars required before any signal may be emitted."""

    @abstractmethod
    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return indicators plus a ``target_weight`` column indexed like ``df``."""

    def targets(self, df: pd.DataFrame) -> pd.Series:
        return self.evaluate(df)["target_weight"]


@dataclass(frozen=True)
class SMACrossoverStrategy(BaseStrategy):
    """Long only trend following with volatility scaled position size.

    Enters when the fast moving average is above the slow one. Rather than
    trading a fixed share count, the position is sized so that an adverse move
    of ``atr_stop_mult`` average true ranges costs ``risk_per_trade`` of
    equity. A quiet symbol therefore gets a larger allocation than a volatile
    one for the same risk budget.
    """

    fast: int = 20
    slow: int = 100
    atr_window: int = 14
    atr_stop_mult: float = 3.0
    risk_per_trade: float = 0.01
    max_weight: float = 0.5

    def __post_init__(self) -> None:
        if self.fast >= self.slow:
            raise ValueError("fast window must be shorter than slow window")
        if not 0 < self.risk_per_trade <= 1:
            raise ValueError("risk_per_trade must be within (0, 1]")

    @property
    def warmup(self) -> int:
        return max(self.slow, self.atr_window) + 1

    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        out["close"] = df["close"]
        out["sma_fast"] = df["close"].rolling(self.fast).mean()
        out["sma_slow"] = df["close"].rolling(self.slow).mean()
        out["atr"] = wilder_atr(df, self.atr_window)

        in_trend = (out["sma_fast"] > out["sma_slow"]).astype(float)
        stop_fraction = (self.atr_stop_mult * out["atr"]) / out["close"]
        weight = (self.risk_per_trade / stop_fraction.replace(0.0, np.nan)).clip(
            upper=self.max_weight
        )

        out["target_weight"] = (in_trend * weight).fillna(0.0)
        out.iloc[: self.warmup, out.columns.get_loc("target_weight")] = 0.0
        out["stop_price"] = out["close"] - self.atr_stop_mult * out["atr"]
        return out


def portfolio_targets(
    strategy: BaseStrategy,
    bars: Dict[str, pd.DataFrame],
    max_gross_exposure: float = 1.0,
) -> pd.DataFrame:
    """Combine per symbol weights and cap total gross exposure.

    When several symbols signal at once the raw weights are scaled down
    proportionally instead of being truncated, which keeps their relative
    sizing intact.
    """
    weights = {
        symbol: strategy.targets(df)
        for symbol, df in bars.items()
        if not df.empty and len(df) > strategy.warmup
    }
    if not weights:
        return pd.DataFrame()

    panel = pd.DataFrame(weights).sort_index().fillna(0.0)
    gross = panel.abs().sum(axis=1)
    scale = (max_gross_exposure / gross).clip(upper=1.0).replace([np.inf, -np.inf], 1.0)
    return panel.mul(scale.fillna(1.0), axis=0)
