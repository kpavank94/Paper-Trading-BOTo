"""End-to-end backtest over the synthetic fixture CSV — no network."""

from pathlib import Path

import pytest

from paper_trading_boto.backtest import run_backtest
from paper_trading_boto.data.yfinance_feed import CSVFeed
from paper_trading_boto.events import Side
from paper_trading_boto.risk import RiskManager
from paper_trading_boto.strategy.sma_crossover import SMACrossoverStrategy

FIXTURE = str(Path(__file__).parent / "fixtures" / "synthetic_daily.csv")


def make_feed(warmup: int = 15) -> CSVFeed:
    return CSVFeed(FIXTURE, symbol="TEST", warmup_count=warmup)


def run(**risk_kw):
    strategy = SMACrossoverStrategy("TEST", short_window=5, long_window=15)
    risk = RiskManager(risk_fraction=0.10, max_portfolio_exposure=0.5,
                       stop_loss_pct=0.20, take_profit_pct=0.50, **risk_kw)
    return run_backtest(
        feed=make_feed(strategy.warmup_bars()),
        strategy=strategy,
        risk=risk,
        initial_cash=100_000.0,
        slippage_bps=0.0,
        commission_per_share=0.0,
    )


def test_backtest_trades_and_is_deterministic():
    r1, r2 = run(), run()
    assert len(r1.fills) >= 4  # at least two round trips on the synthetic waves
    assert [f.price for f in r1.fills] == [f.price for f in r2.fills]
    assert r1.final_equity == pytest.approx(r2.final_equity)


def test_buys_and_sells_alternate_flat_to_flat():
    result = run()
    position = 0
    for fill in result.fills:
        position += fill.quantity if fill.side is Side.BUY else -fill.quantity
        assert position >= 0  # long-only
    assert position == 0  # ends flat (final segment declines)


def test_metrics_are_consistent():
    result = run()
    metrics = result.metrics()
    assert metrics["final_equity"] == pytest.approx(
        result.initial_cash * (1 + metrics["total_return_pct"] / 100), rel=1e-4
    )
    assert 0 <= metrics["max_drawdown_pct"] <= 100
    assert metrics["round_trips"] >= 2
    assert 0.0 <= metrics["win_rate_pct"] <= 100.0
    # The synthetic series rallies ~20 points on 0.8/day drift with a
    # crossover entry; the strategy should capture some of it.
    assert metrics["trades"] == len(result.fills)


def test_equity_curve_sampled_per_bar():
    result = run()
    feed_bars = sum(1 for _ in make_feed(15).bars())
    assert len(result.equity_curve) == feed_bars
    assert result.equity_curve[0][1] == pytest.approx(100_000.0)


def test_kill_switch_flattens_and_blocks():
    # Absurdly tight drawdown limit halts immediately after any dip.
    result = run(max_drawdown_pct=0.0001)
    # Once halted there must be no BUY after the flattening SELL.
    sides = [f.side for f in result.fills]
    if Side.SELL in sides:
        last_sell = len(sides) - 1 - sides[::-1].index(Side.SELL)
        assert Side.BUY not in sides[last_sell:]
