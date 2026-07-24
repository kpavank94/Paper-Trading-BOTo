"""Regression tests for the trade-safety fixes. All offline.

Each test pins one defect found in the order path so it cannot silently return.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from paper_trading_boto.brokers.base import plan_orders
from paper_trading_boto.brokers.ibkr import IBKRBroker
from paper_trading_boto.config import Settings
from paper_trading_boto.cost_basis import Position
from paper_trading_boto.risk_management import PortfolioRiskManager

EASTERN = ZoneInfo("America/New_York")


# ---------------------------------------------------------------- plan_orders
def test_full_exit_is_never_blocked_by_min_notional():
    """A leftover holding worth less than the dust threshold must still close."""
    intents = plan_orders({"SPY": 0.0}, {"SPY": 40.0}, 100_000.0, {"SPY": 1}, min_notional=50.0)
    assert [(i.symbol, i.delta_shares) for i in intents] == [("SPY", -1)]


def test_untargeted_holding_without_price_is_closed():
    intents = plan_orders(
        {"SPY": 0.5}, {"SPY": 400.0}, 100_000.0, held={"SPY": 10, "TSLA": 500}
    )
    by_symbol = {i.symbol: i.delta_shares for i in intents}
    assert by_symbol["TSLA"] == -500  # closed despite no price
    assert by_symbol["SPY"] == 115     # 0.5 * 100k / 400 = 125, from 10 held


def test_short_target_truncates_toward_zero():
    """floor() would size -167; truncation must never oversize a short."""
    intents = plan_orders({"SPY": -0.5}, {"SPY": 300.0}, 100_000.0, {})
    assert intents[0].delta_shares == -166  # int(-166.67), not floor(-166.67) == -167


def test_dust_rebalance_still_filtered():
    """The exit exemption must not leak into ordinary tiny adjustments."""
    assert plan_orders({"SPY": 0.0001}, {"SPY": 400.0}, 100_000.0, {}) == []


# ----------------------------------------------------------- drawdown kill switch
def test_drawdown_halt_survives_restart(tmp_path):
    state = str(tmp_path / "risk_state.json")
    r1 = PortfolioRiskManager(max_drawdown_stop=0.20, state_path=state)
    r1.update_equity(100_000.0)
    assert r1.update_equity(75_000.0) is True  # 25% drawdown -> halt

    # A fresh process (new instance) at the same equity must stay halted.
    r2 = PortfolioRiskManager(max_drawdown_stop=0.20, state_path=state)
    assert r2.halted is True
    assert r2.update_equity(75_000.0) is True


def test_drawdown_peak_high_water_persists(tmp_path):
    state = str(tmp_path / "risk_state.json")
    PortfolioRiskManager(max_drawdown_stop=0.20, state_path=state).update_equity(200_000.0)
    # New run sees only 170k (a 15% drop) but the persisted peak is 200k -> 15% < 20%.
    r = PortfolioRiskManager(max_drawdown_stop=0.20, state_path=state)
    assert r.update_equity(170_000.0) is False
    assert r.update_equity(159_000.0) is True  # 20.5% from the remembered peak


# --------------------------------------------------------------- cost basis
def test_sell_crossing_zero_realizes_only_owned_shares():
    p = Position()
    p.update("BUY", 10, 100.0)
    realized = p.update("SELL", 15, 110.0)   # only 10 were held
    assert realized == pytest.approx(100.0)  # not 150
    assert p.quantity == -5 and p.avg_cost == pytest.approx(110.0)


def test_buy_covering_short_realizes_pnl():
    p = Position()
    p.update("SELL", 10, 100.0)              # open short at 100
    realized = p.update("BUY", 5, 80.0)      # cover half at 80
    assert realized == pytest.approx(100.0)  # +$20 * 5
    assert p.quantity == -5 and p.avg_cost == pytest.approx(100.0)


def test_partial_reduction_keeps_avg_cost():
    p = Position()
    p.update("BUY", 10, 100.0)
    p.update("BUY", 10, 120.0)               # avg 110
    realized = p.update("SELL", 5, 130.0)
    assert realized == pytest.approx(100.0)  # (130-110)*5
    assert p.quantity == 15 and p.avg_cost == pytest.approx(110.0)


# ------------------------------------------------------------ IBKR session gate
def _broker_shell() -> IBKRBroker:
    return object.__new__(IBKRBroker)  # market_is_open uses no instance state


@pytest.mark.parametrize(
    "when,expected",
    [
        (dt.datetime(2026, 7, 22, 11, 0, tzinfo=EASTERN), True),   # Wed 11:00
        (dt.datetime(2026, 7, 22, 8, 0, tzinfo=EASTERN), False),   # Wed pre-open
        (dt.datetime(2026, 7, 22, 20, 0, tzinfo=EASTERN), False),  # Wed after close
        (dt.datetime(2026, 7, 25, 12, 0, tzinfo=EASTERN), False),  # Saturday
    ],
)
def test_ibkr_market_gate_is_not_always_open(when, expected):
    assert _broker_shell().market_is_open(now=when) is expected


def test_ibkr_equity_refuses_fabricated_value():
    class _Iface:
        def get_account_summary(self):
            return None  # TWS unreachable / no data

    b = object.__new__(IBKRBroker)
    b.interface = _Iface()
    b.settings = Settings(starting_equity=100_000.0)
    with pytest.raises(RuntimeError):
        b.equity()


# --------------------------------------------- runner aborts on an unreadable book
class _FakeData:
    def __init__(self, bars):
        self._bars = bars

    def daily_bars(self, lookback_days=None):
        return self._bars

    def last_prices(self, bars):
        return {s: float(df["close"].iloc[-1]) for s, df in bars.items() if not df.empty}


class _BlindBroker:
    """Reports equity fine but cannot read the book — the IBKR failure mode."""

    def market_is_open(self):
        return True

    def equity(self):
        return 100_000.0

    def positions(self):
        raise RuntimeError("socket read failed")

    def working_symbols(self):
        return []

    submitted: list = []

    def submit_market_order(self, symbol, quantity, action):
        self.submitted.append((symbol, quantity, action))
        return "oid"

    def flatten(self):
        pass


def test_runner_skips_rebalance_when_book_unreadable(tmp_path, monkeypatch):
    from paper_trading_boto import runner as runner_mod
    from paper_trading_boto.tests.conftest import make_bars

    bars = {"AAA": make_bars(600, drift=0.002)}
    monkeypatch.setattr(runner_mod, "MarketData", lambda settings: _FakeData(bars))

    settings = dataclasses.replace(Settings(), report_dir=str(tmp_path))
    broker = _BlindBroker()
    broker.submitted = []
    r = runner_mod.Runner(settings, broker=broker)

    intents = r.rebalance(dry_run=False)
    assert intents == []            # aborted, not proceeded on an empty book
    assert broker.submitted == []   # and nothing was sent
