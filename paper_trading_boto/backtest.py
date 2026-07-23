"""Backtest runner: wire a historical feed to the SimulatedBroker.

Produces a :class:`BacktestResult` with an equity curve and the summary
metrics that matter for comparing strategy variants: total return, max
drawdown, (annualized) Sharpe ratio and per-round-trip win rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .broker.sim import SimulatedBroker
from .data.base import DataFeed
from .engine import Engine
from .events import Bar, Fill, Side
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy.base import Strategy


@dataclass
class BacktestResult:
    initial_cash: float
    final_equity: float
    equity_curve: List[Tuple[Bar, float]] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    round_trips: List[float] = field(default_factory=list)  # realized PnL per exit

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_cash - 1.0

    @property
    def max_drawdown(self) -> float:
        peak, max_dd = -math.inf, 0.0
        for _, equity in self.equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, 1.0 - equity / peak)
        return max_dd

    def sharpe(self, periods_per_year: int = 252) -> float:
        """Annualized Sharpe over per-bar equity returns (risk-free = 0)."""
        values = [equity for _, equity in self.equity_curve]
        if len(values) < 3:
            return 0.0
        returns = [b / a - 1.0 for a, b in zip(values, values[1:]) if a > 0]
        n = len(returns)
        mean = sum(returns) / n
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return mean / std * math.sqrt(periods_per_year)

    @property
    def win_rate(self) -> float:
        if not self.round_trips:
            return 0.0
        return sum(1 for pnl in self.round_trips if pnl > 0) / len(self.round_trips)

    def metrics(self) -> Dict[str, float]:
        return {
            "initial_cash": self.initial_cash,
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "sharpe": round(self.sharpe(), 2),
            "trades": len(self.fills),
            "round_trips": len(self.round_trips),
            "win_rate_pct": round(self.win_rate * 100, 1),
        }


def run_backtest(
    feed: DataFeed,
    strategy: Strategy,
    risk: RiskManager,
    initial_cash: float = 100_000.0,
    slippage_bps: float = 1.0,
    commission_per_share: float = 0.005,
) -> BacktestResult:
    broker = SimulatedBroker(
        initial_cash=initial_cash,
        slippage_bps=slippage_bps,
        commission_per_share=commission_per_share,
    )
    result = BacktestResult(initial_cash=initial_cash, final_equity=initial_cash)
    broker.on_fill(result.fills.append)

    engine = Engine(
        feed=feed,
        strategy=strategy,
        risk=risk,
        broker=broker,
        portfolio=Portfolio(initial_cash=initial_cash),
        on_bar_end=lambda bar: result.equity_curve.append((bar, broker.equity())),
    )
    engine.run()
    result.final_equity = broker.equity()

    # Round trips: realized PnL recorded on each position-reducing fill.
    replay = Portfolio(initial_cash=initial_cash)
    for fill in result.fills:
        realized = replay.apply_fill(fill)
        if fill.side is Side.SELL and realized != 0.0:
            result.round_trips.append(realized)

    return result
