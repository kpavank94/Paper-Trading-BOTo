import datetime as dt
from typing import List

from paper_trading_boto.events import Bar, SignalAction
from paper_trading_boto.strategy.sma_crossover import SMACrossoverStrategy


def bars_from_closes(closes: List[float], symbol="AAPL") -> List[Bar]:
    base = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    return [
        Bar(symbol=symbol, timestamp=base + dt.timedelta(days=i),
            open=c, high=c, low=c, close=c, volume=1.0)
        for i, c in enumerate(closes)
    ]


def run(strategy: SMACrossoverStrategy, closes: List[float]):
    signals = []
    for bar in bars_from_closes(closes):
        signal = strategy.on_bar(bar)
        if signal is not None:
            signals.append(signal)
    return signals


def test_no_signal_during_warmup():
    strategy = SMACrossoverStrategy("AAPL", short_window=2, long_window=4)
    assert run(strategy, [100, 100, 100]) == []


def test_cross_up_emits_enter_long_once():
    strategy = SMACrossoverStrategy("AAPL", short_window=2, long_window=4)
    # Flat then rising: short MA crosses above long MA exactly once.
    signals = run(strategy, [100, 100, 100, 100, 100, 105, 110, 115, 120])
    actions = [s.action for s in signals]
    assert actions == [SignalAction.ENTER_LONG]


def test_cross_down_emits_exit_long():
    strategy = SMACrossoverStrategy("AAPL", short_window=2, long_window=4)
    closes = [100, 100, 100, 100, 105, 110, 115, 110, 100, 90, 85, 80]
    signals = run(strategy, closes)
    actions = [s.action for s in signals]
    assert actions == [SignalAction.ENTER_LONG, SignalAction.EXIT_LONG]


def test_no_reentry_while_short_ma_stays_above():
    """Regression: the old level-comparison logic re-entered on every tick
    while short MA > long MA; crossover logic must signal only on the cross."""
    strategy = SMACrossoverStrategy("AAPL", short_window=2, long_window=4)
    closes = [100, 100, 100, 100, 100, 110, 120, 130, 140, 150, 160]
    signals = run(strategy, closes)
    assert len(signals) == 1


def test_warmup_history_enables_immediate_signals():
    strategy = SMACrossoverStrategy("AAPL", short_window=2, long_window=4)
    assert strategy.warmup_bars() == 4
    strategy.on_start(bars_from_closes([100, 100, 100, 100, 100]))
    # First live bar continues an uptrend that crosses immediately.
    signals = run(strategy, [106, 112])
    assert [s.action for s in signals] == [SignalAction.ENTER_LONG]


def test_rejects_bad_windows():
    import pytest
    with pytest.raises(ValueError):
        SMACrossoverStrategy("AAPL", short_window=5, long_window=5)
