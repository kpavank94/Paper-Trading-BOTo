#!/usr/bin/env python3
"""Command line entry point for Paper Trading BOTo.

Examples
--------
Backtest the default 20/100 crossover on the configured symbols::

    python -m paper_trading_boto.bot backtest --symbols SPY,QQQ --out equity.csv

Dry run a single rebalance (logs intended orders, sends nothing)::

    python -m paper_trading_boto.bot once

Send real paper orders and then run continuously::

    python -m paper_trading_boto.bot once --live
    python -m paper_trading_boto.bot loop --live

Credentials and defaults come from .env, so no secret is ever passed as an
argument. See .env.example.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from typing import Optional

from .backtest import run_backtest
from .config import Settings
from .data import MarketData
from .runner import Runner, build_strategy
from .strategy import portfolio_targets
from .utils.logging_config import configure_logging


def load_settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    overrides = {}
    if args.symbols:
        overrides["symbols"] = tuple(
            s.strip().upper() for s in args.symbols.split(",") if s.strip()
        )
    if args.broker:
        overrides["broker"] = args.broker
    strategy_overrides = {
        key: getattr(args, key)
        for key in ("fast", "slow", "atr_stop_mult", "risk_per_trade")
        if getattr(args, key, None) is not None
    }
    if strategy_overrides:
        overrides["strategy"] = dataclasses.replace(settings.strategy, **strategy_overrides)
    return dataclasses.replace(settings, **overrides) if overrides else settings


def cmd_backtest(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    strategy = build_strategy(settings)
    bars = MarketData(settings).daily_bars()
    targets = portfolio_targets(strategy, bars, settings.strategy.max_gross_exposure)
    result = run_backtest(
        bars,
        targets,
        starting_equity=settings.starting_equity,
        slippage_bps=settings.slippage_bps,
        commission_bps=settings.commission_bps,
    )
    print(json.dumps(result.metrics.as_dict(), indent=2, default=float))
    if args.out:
        result.equity.rename("equity").to_csv(args.out)
    return 0


def cmd_once(args: argparse.Namespace) -> int:
    runner = Runner(load_settings(args))
    runner.broker.connect()
    try:
        runner.rebalance(dry_run=not args.live)
    finally:
        runner.report()
        runner.broker.disconnect()
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    Runner(load_settings(args)).loop(
        minutes_before_close=args.minutes_before_close, dry_run=not args.live
    )
    return 0


def cmd_flatten(args: argparse.Namespace) -> int:
    runner = Runner(load_settings(args))
    runner.broker.connect()
    try:
        runner.broker.flatten()
    finally:
        runner.broker.disconnect()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper_trading_boto", description="Run or evaluate a trading strategy"
    )
    parser.add_argument("--broker", choices=["alpaca", "ibkr"], default=None)
    parser.add_argument("--symbols", default=None, help="comma separated tickers")
    parser.add_argument("--fast", type=int, default=None, help="fast SMA window")
    parser.add_argument("--slow", type=int, default=None, help="slow SMA window")
    parser.add_argument("--atr-stop-mult", dest="atr_stop_mult", type=float, default=None)
    parser.add_argument("--risk-per-trade", dest="risk_per_trade", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser("backtest", help="evaluate the strategy on history")
    backtest.add_argument("--out", default=None, help="write the equity curve to this CSV")
    backtest.set_defaults(func=cmd_backtest)

    once = sub.add_parser("once", help="single rebalance")
    once.add_argument("--live", action="store_true", help="send orders instead of a dry run")
    once.set_defaults(func=cmd_once)

    loop = sub.add_parser("loop", help="rebalance once per session")
    loop.add_argument("--live", action="store_true", help="send orders instead of a dry run")
    loop.add_argument("--minutes-before-close", type=int, default=15)
    loop.set_defaults(func=cmd_loop)

    flatten = sub.add_parser("flatten", help="close every open position")
    flatten.set_defaults(func=cmd_flatten)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(
        name="paper_trading_boto",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )
    logging.getLogger().setLevel(logging.DEBUG if args.verbose else logging.INFO)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
