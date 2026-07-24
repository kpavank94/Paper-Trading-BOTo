from __future__ import annotations

import numpy as np
import pandas as pd

from paper_trading_boto.backtest import run_backtest
from paper_trading_boto.strategy import SMACrossoverStrategy, portfolio_targets
from paper_trading_boto.tests.conftest import make_bars


def test_flat_book_leaves_equity_unchanged(bars):
    targets = pd.DataFrame({"AAA": 0.0}, index=bars.index)
    result = run_backtest({"AAA": bars}, targets, starting_equity=1000.0)
    assert np.isclose(result.equity.iloc[-1], 1000.0)
    assert result.metrics.ann_turnover == 0.0


def test_full_weight_matches_buy_and_hold(bars):
    """Entry is at the second bar's open, so the curve must equal that hold."""
    targets = pd.DataFrame({"AAA": 1.0}, index=bars.index)
    result = run_backtest({"AAA": bars}, targets, starting_equity=1000.0, slippage_bps=0.0)
    expected = 1000.0 * bars["close"].iloc[-1] / bars["open"].iloc[1]
    assert abs(result.equity.iloc[-1] / expected - 1) < 1e-9


def test_costs_reduce_equity(bars):
    targets = portfolio_targets(SMACrossoverStrategy(), {"AAA": bars})
    free = run_backtest({"AAA": bars}, targets, slippage_bps=0.0)
    charged = run_backtest({"AAA": bars}, targets, slippage_bps=25.0)
    assert charged.equity.iloc[-1] < free.equity.iloc[-1]


def test_signal_shifted_one_bar(bars):
    """A weight set at close(t) must not earn close(t-1) to close(t)."""
    targets = pd.DataFrame({"AAA": 0.0}, index=bars.index)
    targets.iloc[10] = 1.0
    result = run_backtest({"AAA": bars}, targets, slippage_bps=0.0)
    assert result.returns.iloc[10] == 0.0
    assert result.returns.iloc[11] != 0.0


def test_metrics_are_coherent():
    frames = {n: make_bars(700, seed=i, drift=0.0004) for i, n in enumerate("AB")}
    targets = portfolio_targets(SMACrossoverStrategy(), frames, 1.0)
    metrics = run_backtest(frames, targets).metrics
    assert metrics.max_drawdown <= 0
    assert 0.0 <= metrics.hit_rate <= 1.0
    assert metrics.avg_gross_exposure > 0
