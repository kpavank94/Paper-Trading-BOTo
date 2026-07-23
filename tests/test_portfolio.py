import datetime as dt

import pytest

from paper_trading_boto.events import Fill, Side
from paper_trading_boto.portfolio import Portfolio, Position

TS = dt.datetime(2025, 1, 2, 15, 0, tzinfo=dt.timezone.utc)


def fill(side: Side, qty: int, price: float, commission: float = 0.0) -> Fill:
    return Fill(symbol="AAPL", side=side, quantity=qty, price=price, timestamp=TS,
                commission=commission)


class TestPosition:
    def test_open_and_average_long(self):
        p = Position()
        assert p.apply_fill(Side.BUY, 10, 100.0) == 0.0
        assert p.apply_fill(Side.BUY, 10, 110.0) == 0.0
        assert p.quantity == 20
        assert p.avg_cost == pytest.approx(105.0)

    def test_long_realized_pnl(self):
        p = Position()
        p.apply_fill(Side.BUY, 10, 100.0)
        realized = p.apply_fill(Side.SELL, 10, 120.0)
        assert realized == pytest.approx(200.0)
        assert p.quantity == 0
        assert p.avg_cost == 0.0

    def test_partial_close_keeps_avg_cost(self):
        p = Position()
        p.apply_fill(Side.BUY, 10, 100.0)
        realized = p.apply_fill(Side.SELL, 4, 110.0)
        assert realized == pytest.approx(40.0)
        assert p.quantity == 6
        assert p.avg_cost == pytest.approx(100.0)

    def test_short_open_and_cover_profit(self):
        """Regression: original code never realized PnL on buy-to-cover."""
        p = Position()
        assert p.apply_fill(Side.SELL, 10, 100.0) == 0.0
        assert p.quantity == -10
        assert p.avg_cost == pytest.approx(100.0)
        realized = p.apply_fill(Side.BUY, 10, 90.0)  # cover below entry = profit
        assert realized == pytest.approx(100.0)
        assert p.quantity == 0

    def test_short_cover_at_loss(self):
        p = Position()
        p.apply_fill(Side.SELL, 5, 50.0)
        realized = p.apply_fill(Side.BUY, 5, 60.0)
        assert realized == pytest.approx(-50.0)

    def test_flip_long_to_short(self):
        """Selling more than held closes the long and opens a short at fill price."""
        p = Position()
        p.apply_fill(Side.BUY, 10, 100.0)
        realized = p.apply_fill(Side.SELL, 15, 110.0)
        assert realized == pytest.approx(100.0)  # only the 10 closed shares realize
        assert p.quantity == -5
        assert p.avg_cost == pytest.approx(110.0)

    def test_flip_short_to_long(self):
        p = Position()
        p.apply_fill(Side.SELL, 10, 100.0)
        realized = p.apply_fill(Side.BUY, 15, 95.0)
        assert realized == pytest.approx(50.0)
        assert p.quantity == 5
        assert p.avg_cost == pytest.approx(95.0)


class TestPortfolio:
    def test_cash_and_equity(self):
        pf = Portfolio(initial_cash=10_000.0)
        pf.apply_fill(fill(Side.BUY, 10, 100.0, commission=1.0))
        assert pf.cash == pytest.approx(10_000.0 - 1_000.0 - 1.0)
        assert pf.quantity("AAPL") == 10
        assert pf.equity({"AAPL": 105.0}) == pytest.approx(8_999.0 + 1_050.0)

    def test_realized_pnl_accumulates_per_symbol(self):
        pf = Portfolio(initial_cash=10_000.0)
        pf.apply_fill(fill(Side.BUY, 10, 100.0))
        pf.apply_fill(fill(Side.SELL, 10, 110.0))
        assert pf.realized_pnl["AAPL"] == pytest.approx(100.0)
        assert pf.total_realized_pnl() == pytest.approx(100.0)
        assert pf.unrealized_pnl("AAPL", 120.0) == 0.0

    def test_short_sale_increases_cash(self):
        pf = Portfolio(initial_cash=10_000.0)
        pf.apply_fill(fill(Side.SELL, 10, 100.0))
        assert pf.cash == pytest.approx(11_000.0)
        assert pf.quantity("AAPL") == -10
        assert pf.equity({"AAPL": 100.0}) == pytest.approx(10_000.0)

    def test_summary(self):
        pf = Portfolio()
        pf.apply_fill(fill(Side.BUY, 10, 100.0))
        s = pf.summary()
        assert s["AAPL"]["quantity"] == 10
        assert s["AAPL"]["avg_cost"] == pytest.approx(100.0)
