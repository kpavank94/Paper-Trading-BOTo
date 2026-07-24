from __future__ import annotations

from paper_trading_boto.brokers.base import plan_orders
from paper_trading_boto.risk_management import PortfolioRiskManager


def test_plan_rounds_down_and_signs_correctly():
    intents = plan_orders(
        target_weights={"SPY": 0.3},
        prices={"SPY": 500.0},
        equity=100_000.0,
        held={},
    )
    assert len(intents) == 1
    assert intents[0].delta_shares == 60 and intents[0].action == "BUY"


def test_untargeted_holdings_are_closed():
    intents = plan_orders(
        target_weights={"SPY": 0.0},
        prices={"SPY": 400.0, "QQQ": 400.0},
        equity=100_000.0,
        held={"SPY": 10, "QQQ": 5},
    )
    assert {i.symbol: i.delta_shares for i in intents} == {"SPY": -10, "QQQ": -5}


def test_dust_and_blocked_symbols_are_skipped():
    assert plan_orders({"SPY": 0.0001}, {"SPY": 400.0}, 100_000.0, {}) == []
    assert plan_orders({"SPY": 0.5}, {"SPY": 400.0}, 100_000.0, {}, blocked={"SPY"}) == []


def test_missing_price_is_not_traded():
    assert plan_orders({"SPY": 0.5}, {}, 100_000.0, {}) == []


def test_drawdown_halt_flattens_targets():
    risk = PortfolioRiskManager(max_drawdown_stop=0.2)
    assert not risk.update_equity(100_000.0)
    assert not risk.update_equity(85_000.0)
    assert risk.update_equity(79_000.0)
    assert risk.apply({"SPY": 0.4}) == {"SPY": 0.0}


def test_gross_exposure_clamp():
    risk = PortfolioRiskManager(max_gross_exposure=1.0, max_weight=0.5)
    out = risk.apply({"A": 0.9, "B": 0.9})
    assert sum(out.values()) <= 1.0 + 1e-9
    assert max(out.values()) <= 0.5 + 1e-9
