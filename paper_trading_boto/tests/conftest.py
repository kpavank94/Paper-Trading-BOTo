from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_bars(n: int = 900, seed: int = 7, drift: float = 0.0003) -> pd.DataFrame:
    """Synthetic OHLCV that behaves like a daily equity series."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.011, n)
    close = 100 * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.003, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.003, n)))
    index = pd.date_range("2019-01-02", periods=n, freq="B", tz="UTC", name="timestamp")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 1e6},
        index=index,
    )


@pytest.fixture
def bars() -> pd.DataFrame:
    return make_bars()
