"""Signal correctness. Nothing here touches the network."""

from __future__ import annotations

import pandas as pd
import pytest

from paper_trading_boto.strategy import (
    SMACrossoverStrategy,
    portfolio_targets,
    wilder_atr,
)
from paper_trading_boto.tests.conftest import make_bars


def test_atr_warms_up_then_stays_positive(bars):
    atr = wilder_atr(bars, 14)
    assert atr.iloc[:13].isna().all()
    assert (atr.dropna() > 0).all()


def test_rejects_inverted_windows():
    with pytest.raises(ValueError):
        SMACrossoverStrategy(fast=100, slow=20)


def test_no_lookahead(bars):
    """Perturbing only the last bar must leave every earlier weight untouched."""
    strategy = SMACrossoverStrategy()
    baseline = strategy.targets(bars)
    shocked = bars.copy()
    shocked.iloc[-1] = shocked.iloc[-1] * 5
    pd.testing.assert_series_equal(baseline.iloc[:-1], strategy.targets(shocked).iloc[:-1])


def test_weights_are_flat_during_warmup(bars):
    strategy = SMACrossoverStrategy()
    assert (strategy.targets(bars).iloc[: strategy.warmup] == 0).all()


def test_quiet_symbol_gets_the_larger_weight():
    """Volatility scaling: same trend, lower vol, bigger position."""
    calm = make_bars(600, seed=11, drift=0.002)
    calm[["open", "high", "low", "close"]] = calm[["open", "high", "low", "close"]]
    wild = calm.copy()
    span = wild["high"] - wild["low"]
    wild["high"] = wild["high"] + span * 4
    wild["low"] = wild["low"] - span * 4

    strategy = SMACrossoverStrategy()
    calm_weight = strategy.targets(calm).iloc[-1]
    wild_weight = strategy.targets(wild).iloc[-1]
    assert calm_weight > 0 and wild_weight > 0
    assert calm_weight > wild_weight


def test_gross_exposure_is_capped():
    bars = {name: make_bars(600, seed=i, drift=0.002) for i, name in enumerate("ABCD")}
    panel = portfolio_targets(SMACrossoverStrategy(), bars, max_gross_exposure=1.0)
    assert not panel.empty
    assert (panel.abs().sum(axis=1) <= 1.0 + 1e-9).all()
