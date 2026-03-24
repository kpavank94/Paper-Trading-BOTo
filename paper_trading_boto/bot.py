#!/usr/bin/env python3
"""
Main entry point for running strategies with Paper Trading BOTo.

This script parses command‑line arguments, loads configuration from
``.env``, connects to the IBKR API, instantiates the requested
strategy and risk manager, and runs a simple tick loop.  At the end
of the session it generates a CSV and HTML report summarising trades
and positions.  Users can modify the loop interval, duration and
strategy parameters via command‑line flags.

Examples
--------

Run a 10/30 SMA crossover strategy on AAPL with 10 shares per trade:

```
python bot.py --symbol AAPL --strategy sma_crossover --short_window 10 --long_window 30 --quantity 10
```

See the README for details on configuration and available options.
"""

from __future__ import annotations

import argparse
import datetime
import os
import signal
import sys
import time
from typing import Optional

from dotenv import load_dotenv

from .ibkr_interface import IBKRInterface, IBKRConnectionParams
from .strategy import SMACrossoverStrategy, BaseStrategy
from .risk_management import RiskManager, FixedFractionalRiskManager
from .cost_basis import CostBasisTracker
from .reporting import ReportGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a trading strategy in paper mode")
    parser.add_argument("--symbol", required=True, help="Ticker symbol to trade, e.g., AAPL")
    parser.add_argument("--strategy", default="sma_crossover", help="Name of strategy to run")
    parser.add_argument("--quantity", type=int, default=10, help="Base position size for each trade")
    parser.add_argument("--short_window", type=int, default=10, help="Short moving average window")
    parser.add_argument("--long_window", type=int, default=30, help="Long moving average window")
    parser.add_argument(
        "--interval", type=float, default=5.0, help="Interval (in seconds) between price polls"
    )
    parser.add_argument(
        "--duration", type=int, default=30, help="Duration of the session in minutes (0 for indefinite)"
    )
    parser.add_argument(
        "--risk_fraction",
        type=float,
        default=0.05,
        help="Maximum fraction of capital to risk on each trade (0 < fraction <= 1)",
    )
    return parser.parse_args()


def load_config() -> IBKRConnectionParams:
    """Load configuration from .env and environment variables."""
    load_dotenv()
    host = os.getenv("TWS_HOST", "127.0.0.1")
    port = int(os.getenv("TWS_PORT", 7497))
    client_id = int(os.getenv("CLIENT_ID", 1))
    account = os.getenv("ACCOUNT")
    return IBKRConnectionParams(host=host, port=port, client_id=client_id, account=account)


def main() -> None:
    args = parse_args()
    params = load_config()

    # Risk manager uses account value; since we cannot query account equity easily via API here,
    # allow override through environment variable or default to 10,000.
    initial_equity = float(os.getenv("ACCOUNT_EQUITY", 10000.0))
    risk_manager = FixedFractionalRiskManager(max_fraction=args.risk_fraction, account_value=initial_equity)
    cost_tracker = CostBasisTracker()

    ibkr = IBKRInterface(params=params, db_path=os.getenv("DB_PATH"))
    ibkr.connect()

    # Instantiate chosen strategy
    strategy: BaseStrategy
    if args.strategy.lower() == "sma_crossover":
        strategy = SMACrossoverStrategy(
            ibkr=ibkr,
            symbol=args.symbol,
            quantity=args.quantity,
            risk_manager=risk_manager,
            cost_tracker=cost_tracker,
            short_window=args.short_window,
            long_window=args.long_window,
        )
    else:
        raise ValueError(f"Unknown strategy: {args.strategy}")

    # Setup termination signal
    stop = False
    def signal_handler(sig, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    strategy.on_start()
    start_time = datetime.datetime.utcnow()
    end_time = start_time + datetime.timedelta(minutes=args.duration) if args.duration > 0 else None

    try:
        while not stop:
            now = datetime.datetime.utcnow()
            if end_time and now >= end_time:
                break
            price = ibkr.get_current_price(args.symbol)
            if price is not None:
                strategy.on_tick(price, now)
            # Check risk manager for exit conditions
            if strategy.position != 0 and risk_manager.should_exit_position(
                entry_price=strategy.entry_price or price, current_price=price or 0.0, position=strategy.position
            ):
                # Close position
                action = "SELL" if strategy.position > 0 else "BUY"
                qty = abs(strategy.position)
                ibkr.place_market_order(args.symbol, qty, action)
                cost_tracker.record_trade(
                    TradeRecord(
                        symbol=args.symbol,
                        action=action,
                        quantity=qty,
                        price=price if price is not None else 0.0,
                        timestamp=now,
                    )
                )
                strategy.position = 0
                strategy.entry_price = None
                ibkr.logger.info(f"Risk manager closed position at {price:.2f}")
            time.sleep(args.interval)
    finally:
        strategy.on_finish()
        ibkr.disconnect()
        # Generate reports
        report_gen = ReportGenerator()
        csv_path = report_gen.generate_csv(cost_tracker.trade_history, cost_tracker)
        html_path = report_gen.generate_html(cost_tracker.trade_history, cost_tracker)
        ibkr.logger.info(f"Trading session complete. Reports saved to {csv_path} and {html_path}.")


if __name__ == "__main__":
    main()