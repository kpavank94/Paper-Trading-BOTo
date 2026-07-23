"""Command-line interface: ``boto backtest | live | webhook``."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from .config import Settings
from .risk import RiskManager
from .strategy import STRATEGIES


def _add_strategy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", required=True, help="Ticker symbol, e.g. AAPL")
    parser.add_argument("--strategy", default="sma_crossover", choices=sorted(STRATEGIES))
    parser.add_argument("--short-window", type=int, default=10)
    parser.add_argument("--long-window", type=int, default=30)


def _build_strategy(args: argparse.Namespace):
    cls = STRATEGIES[args.strategy]
    return cls(args.symbol, short_window=args.short_window, long_window=args.long_window)


def _risk_from_settings(settings: Settings) -> RiskManager:
    return RiskManager(
        risk_fraction=settings.risk_fraction,
        max_portfolio_exposure=settings.max_portfolio_exposure,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        max_drawdown_pct=settings.max_drawdown_pct,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="boto", description="Paper Trading BOTo")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_backtest = sub.add_parser("backtest", help="Run a backtest on yfinance data")
    _add_strategy_args(p_backtest)
    p_backtest.add_argument("--start", required=True, type=dt.date.fromisoformat)
    p_backtest.add_argument("--end", required=True, type=dt.date.fromisoformat)
    p_backtest.add_argument("--interval", default="1d", help="yfinance interval (1d, 1h, 5m)")
    p_backtest.add_argument("--cash", type=float, default=100_000.0)

    p_live = sub.add_parser("live", help="Trade live against an IBKR paper account")
    _add_strategy_args(p_live)
    p_live.add_argument("--bar-seconds", type=int, default=60)
    p_live.add_argument("--duration", type=int, default=0,
                        help="Session length in minutes (0 = until Ctrl-C)")

    p_webhook = sub.add_parser("webhook", help="Run the TradingView webhook service")
    p_webhook.add_argument("--host", default="127.0.0.1")
    p_webhook.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    settings = Settings.from_env()

    if args.command == "backtest":
        from .backtest import run_backtest
        from .data.yfinance_feed import YFinanceFeed
        from .reporting import ReportGenerator

        strategy = _build_strategy(args)
        feed = YFinanceFeed(args.symbol, args.start, args.end, interval=args.interval)
        result = run_backtest(feed, strategy, _risk_from_settings(settings),
                              initial_cash=args.cash)
        metrics = result.metrics()
        width = max(len(k) for k in metrics)
        for key, value in metrics.items():
            print(f"{key:<{width}}  {value}")

        reports = ReportGenerator(settings.report_dir)
        from .portfolio import Portfolio

        replay = Portfolio(initial_cash=args.cash)
        for fill in result.fills:
            replay.apply_fill(fill)
        html = reports.generate_html(result.fills, replay, metrics=metrics)
        print(f"report: {html}")
        return 0

    if args.command == "live":
        from .live import run_live

        run_live(
            _build_strategy(args),
            settings,
            bar_seconds=args.bar_seconds,
            duration_minutes=args.duration,
        )
        return 0

    if args.command == "webhook":
        import uvicorn

        if not settings.tradingview_secret:
            print("Refusing to start: TRADINGVIEW_SECRET is not set (auth would be "
                  "disabled). Set it in .env.", file=sys.stderr)
            return 2
        uvicorn.run("paper_trading_boto.webhook_service:app",
                    host=args.host, port=args.port)
        return 0

    return 1  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
