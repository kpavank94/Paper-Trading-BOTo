"""Paper Trading BOTo: a bar driven equities trading framework.

Public surface::

    from paper_trading_boto import Settings, Runner, SMACrossoverStrategy
    from paper_trading_boto import run_backtest, portfolio_targets
"""

from .backtest import BacktestResult, Metrics, run_backtest
from .config import Settings
from .cost_basis import CostBasisTracker, TradeRecord
from .risk_management import FixedFractionalRiskManager, PortfolioRiskManager, RiskManager
from .strategy import BaseStrategy, SMACrossoverStrategy, portfolio_targets, wilder_atr

__all__ = [
    "BacktestResult",
    "BaseStrategy",
    "CostBasisTracker",
    "FixedFractionalRiskManager",
    "Metrics",
    "PortfolioRiskManager",
    "RiskManager",
    "SMACrossoverStrategy",
    "Settings",
    "TradeRecord",
    "portfolio_targets",
    "run_backtest",
    "wilder_atr",
]


def __getattr__(name: str):
    """Lazily expose components that pull in optional broker dependencies."""
    if name in {"Runner", "build_strategy"}:
        from . import runner

        return getattr(runner, name)
    if name in {"MarketData"}:
        from .data import MarketData

        return MarketData
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
