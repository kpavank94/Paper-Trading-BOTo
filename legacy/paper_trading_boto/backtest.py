"""Backtest engine.

The repository previously had no way to evaluate a strategy other than running
it live, so there was no evidence any parameter choice was sound.

Execution model: a target weight formed at the close of day t is filled at the
open of day t+1. Between close(t) and open(t+1) the book still carries the
weight established at open(t), so the overnight gap is attributed to the older
weight. Naive close to close backtests implicitly assume you can trade at the
same close that produced the signal, which flatters trend systems badly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class Metrics:
    start: str
    end: str
    total_return: float
    cagr: float
    ann_volatility: float
    sharpe: float
    max_drawdown: float
    calmar: float
    avg_gross_exposure: float
    ann_turnover: float
    hit_rate: float

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    exposure: pd.DataFrame
    metrics: Metrics


def _common_index(bars: Dict[str, pd.DataFrame], targets: pd.DataFrame) -> pd.DatetimeIndex:
    index = targets.index
    for symbol in targets.columns:
        index = index.intersection(bars[symbol].index)
    return pd.DatetimeIndex(sorted(index))


def run_backtest(
    bars: Dict[str, pd.DataFrame],
    targets: pd.DataFrame,
    starting_equity: float = 100_000.0,
    slippage_bps: float = 2.0,
    commission_bps: float = 0.0,
) -> BacktestResult:
    if targets.empty:
        raise ValueError("targets frame is empty; check the warmup period and symbols")

    index = _common_index(bars, targets)
    if len(index) < 2:
        raise ValueError("not enough overlapping bars to run a backtest")
    targets = targets.reindex(index).fillna(0.0)
    cost_rate = (slippage_bps + commission_bps) / 10_000.0

    overnight = pd.Series(0.0, index=index)  # close(t-1) to open(t)
    intraday = pd.Series(0.0, index=index)  # open(t) to close(t)
    costs = pd.Series(0.0, index=index)
    exposure = pd.DataFrame(0.0, index=index, columns=targets.columns)

    for symbol in targets.columns:
        df = bars[symbol].reindex(index)
        gap = (df["open"] / df["close"].shift(1) - 1.0).fillna(0.0)
        session = (df["close"] / df["open"] - 1.0).fillna(0.0)

        held = targets[symbol].shift(1).fillna(0.0)  # filled at this bar's open
        previously_held = held.shift(1).fillna(0.0)

        overnight += previously_held * gap
        intraday += held * session
        costs += (held - previously_held).abs() * cost_rate
        exposure[symbol] = held

    returns = ((1.0 + overnight) * (1.0 + intraday) - 1.0 - costs).fillna(0.0)
    equity = starting_equity * (1.0 + returns).cumprod()
    return BacktestResult(equity, returns, exposure, compute_metrics(equity, returns, exposure))


def compute_metrics(
    equity: pd.Series, returns: pd.Series, exposure: pd.DataFrame
) -> Metrics:
    invested = returns[exposure.abs().sum(axis=1) > 0]
    years = max(len(returns) / TRADING_DAYS, 1e-9)
    sigma = float(returns.std(ddof=0))
    drawdown = float((equity / equity.cummax() - 1.0).min())
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)
    return Metrics(
        start=str(equity.index[0].date()),
        end=str(equity.index[-1].date()),
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1.0),
        cagr=cagr,
        ann_volatility=float(sigma * np.sqrt(TRADING_DAYS)),
        sharpe=float(returns.mean() / sigma * np.sqrt(TRADING_DAYS)) if sigma else 0.0,
        max_drawdown=drawdown,
        calmar=float(cagr / abs(drawdown)) if drawdown else 0.0,
        avg_gross_exposure=float(exposure.abs().sum(axis=1).mean()),
        ann_turnover=float(exposure.diff().abs().sum(axis=1).mean() * TRADING_DAYS),
        hit_rate=float((invested > 0).mean()) if len(invested) else 0.0,
    )
