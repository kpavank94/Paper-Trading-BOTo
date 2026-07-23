import datetime as dt
import math

import pytest

from paper_trading_boto.events import Side, Signal, SignalAction
from paper_trading_boto.risk import RiskManager

TS = dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc)


def enter(symbol="AAPL") -> Signal:
    return Signal(symbol=symbol, action=SignalAction.ENTER_LONG, timestamp=TS)


def leave(symbol="AAPL") -> Signal:
    return Signal(symbol=symbol, action=SignalAction.EXIT_LONG, timestamp=TS)


class TestShouldExit:
    def test_missing_price_never_exits(self):
        """Regression for bot.py passing `price or 0.0`: one missed tick
        must NOT liquidate the position."""
        risk = RiskManager()
        assert risk.should_exit(entry_price=100.0, current_price=None, position=10) is False
        assert risk.should_exit(100.0, float("nan"), 10) is False
        assert risk.should_exit(100.0, math.inf, 10) is False

    def test_stop_loss_and_take_profit(self):
        risk = RiskManager(stop_loss_pct=0.05, take_profit_pct=0.10)
        assert risk.should_exit(100.0, 94.9, 10) is True
        assert risk.should_exit(100.0, 110.1, 10) is True
        assert risk.should_exit(100.0, 100.0, 10) is False


class TestSizing:
    def test_position_sized_from_current_equity(self):
        risk = RiskManager(risk_fraction=0.05, max_portfolio_exposure=1.0)
        order = risk.order_for_signal(enter(), price=100.0, equity=100_000.0,
                                      current_position=0)
        assert order is not None
        assert order.quantity == 50  # 5% of 100k / 100
        assert order.side is Side.BUY
        assert order.stop_loss_price == pytest.approx(95.0)

    def test_exposure_cap_limits_size(self):
        risk = RiskManager(risk_fraction=0.5, max_portfolio_exposure=0.1)
        order = risk.order_for_signal(enter(), price=100.0, equity=10_000.0,
                                      current_position=0, current_exposure=900.0)
        assert order is not None
        assert order.quantity == 1  # headroom = 1000-900 = 100 -> 1 share

    def test_no_entry_when_already_long(self):
        risk = RiskManager()
        assert risk.order_for_signal(enter(), 100.0, 100_000.0, current_position=10) is None

    def test_no_entry_on_bad_price(self):
        risk = RiskManager()
        assert risk.order_for_signal(enter(), float("nan"), 100_000.0, 0) is None
        assert risk.order_for_signal(enter(), 0.0, 100_000.0, 0) is None

    def test_exit_sells_entire_position(self):
        risk = RiskManager()
        order = risk.order_for_signal(leave(), 100.0, 100_000.0, current_position=30)
        assert order is not None
        assert order.side is Side.SELL
        assert order.quantity == 30

    def test_exit_without_position_is_noop(self):
        risk = RiskManager()
        assert risk.order_for_signal(leave(), 100.0, 100_000.0, current_position=0) is None


class TestKillSwitch:
    def test_halts_past_max_drawdown_and_blocks_entries(self):
        risk = RiskManager(max_drawdown_pct=0.20)
        risk.update_equity(100_000.0)
        risk.update_equity(90_000.0)
        assert risk.halted is False
        risk.update_equity(79_000.0)  # 21% drawdown
        assert risk.halted is True
        assert risk.order_for_signal(enter(), 100.0, 79_000.0, 0) is None
        # Exits still allowed while halted.
        assert risk.order_for_signal(leave(), 100.0, 79_000.0, 10) is not None
