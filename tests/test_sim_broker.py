import datetime as dt

import pytest

from paper_trading_boto.broker.sim import SimulatedBroker
from paper_trading_boto.events import Bar, OrderRequest, OrderType, Side


def bar(o, h, l, c, minute=0, symbol="AAPL") -> Bar:
    ts = dt.datetime(2025, 1, 2, 15, minute, tzinfo=dt.timezone.utc)
    return Bar(symbol=symbol, timestamp=ts, open=o, high=h, low=l, close=c, volume=1000)


def make_broker(**kw) -> SimulatedBroker:
    defaults = dict(initial_cash=100_000.0, slippage_bps=0.0, commission_per_share=0.0,
                    commission_min=0.0)
    defaults.update(kw)
    return SimulatedBroker(**defaults)


def test_market_order_fills_at_next_bar_open():
    broker = make_broker()
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(OrderRequest(symbol="AAPL", side=Side.BUY, quantity=10))
    assert fills == []  # nothing fills until a bar arrives
    broker.process_bar(bar(101.0, 102.0, 100.0, 101.5, minute=1))
    assert len(fills) == 1
    assert fills[0].price == pytest.approx(101.0)
    assert broker.positions() == {"AAPL": 10}


def test_slippage_hurts_both_directions():
    broker = make_broker(slippage_bps=10.0)  # 0.1%
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(OrderRequest(symbol="AAPL", side=Side.BUY, quantity=10))
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1))
    assert fills[0].price == pytest.approx(100.10)  # buy pays up
    broker.submit_order(OrderRequest(symbol="AAPL", side=Side.SELL, quantity=10))
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=2))
    assert fills[1].price == pytest.approx(99.90)  # sell receives less


def test_commission_minimum_applies():
    broker = make_broker(commission_per_share=0.005, commission_min=1.0)
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(OrderRequest(symbol="AAPL", side=Side.BUY, quantity=10))
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1))
    assert fills[0].commission == pytest.approx(1.0)  # 10 * 0.005 = 0.05 < min


def test_limit_order_waits_for_price():
    broker = make_broker()
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(
        OrderRequest(symbol="AAPL", side=Side.BUY, quantity=5,
                     order_type=OrderType.LIMIT, limit_price=98.0)
    )
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1))  # low 99 > 98
    assert fills == []
    broker.process_bar(bar(99.0, 100.0, 97.5, 98.5, minute=2))  # low crosses 98
    assert len(fills) == 1
    assert fills[0].price == pytest.approx(98.0)


def test_attached_stop_liquidates_long():
    broker = make_broker()
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(
        OrderRequest(symbol="AAPL", side=Side.BUY, quantity=10, stop_loss_price=95.0)
    )
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1))  # entry @100
    broker.process_bar(bar(99.0, 99.5, 96.0, 97.0, minute=2))     # stop not hit (low 96 > 95)
    assert len(fills) == 1
    broker.process_bar(bar(96.0, 96.5, 94.0, 94.5, minute=3))     # low 94 <= 95 -> stop
    assert len(fills) == 2
    assert fills[1].side is Side.SELL
    assert fills[1].price == pytest.approx(95.0)
    assert broker.positions() == {}


def test_stop_gapping_through_fills_at_open():
    broker = make_broker()
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(
        OrderRequest(symbol="AAPL", side=Side.BUY, quantity=10, stop_loss_price=95.0)
    )
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1))
    broker.process_bar(bar(90.0, 91.0, 89.0, 90.5, minute=2))  # gaps below the stop
    assert fills[1].price == pytest.approx(90.0)  # filled at open, not the stop price


def test_orders_for_other_symbols_stay_queued():
    broker = make_broker()
    fills = []
    broker.on_fill(fills.append)
    broker.submit_order(OrderRequest(symbol="MSFT", side=Side.BUY, quantity=5))
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1, symbol="AAPL"))
    assert fills == []
    broker.process_bar(bar(300.0, 301.0, 299.0, 300.5, minute=2, symbol="MSFT"))
    assert len(fills) == 1


def test_cancel_removes_open_order():
    broker = make_broker()
    fills = []
    broker.on_fill(fills.append)
    order_id = broker.submit_order(OrderRequest(symbol="AAPL", side=Side.BUY, quantity=5))
    broker.cancel_order(order_id)
    broker.process_bar(bar(100.0, 101.0, 99.0, 100.5, minute=1))
    assert fills == []


def test_equity_marks_to_market():
    broker = make_broker()
    broker.submit_order(OrderRequest(symbol="AAPL", side=Side.BUY, quantity=10))
    broker.process_bar(bar(100.0, 101.0, 99.0, 110.0, minute=1))
    # cash = 100k - 1000; position marked at close 110 -> equity = 99k + 1100
    assert broker.equity() == pytest.approx(100_100.0)
