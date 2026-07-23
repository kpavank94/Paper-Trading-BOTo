"""Live paper-trading runner: IBKR feed + IBKR broker + engine.

Adds what the old ``bot.py`` loop lacked: startup position
reconciliation, fills as the only source of position truth, broker-side
stops, graceful SIGINT/SIGTERM shutdown and an end-of-session report.
"""

from __future__ import annotations

import datetime as dt
import logging
import signal
import threading
from typing import Optional

from .broker.ibkr import IBKRBroker
from .config import Settings
from .data.ibkr_feed import IBKRFeed
from .engine import Engine
from .portfolio import Portfolio
from .reporting import ReportGenerator
from .risk import RiskManager
from .strategy.base import Strategy

logger = logging.getLogger(__name__)


def run_live(
    strategy: Strategy,
    settings: Settings,
    bar_seconds: int = 60,
    duration_minutes: int = 0,
) -> Portfolio:
    broker = IBKRBroker(
        host=settings.tws_host,
        port=settings.tws_port,
        client_id=settings.client_id,
        account=settings.account,
    )
    broker.connect()

    existing = broker.positions().get(strategy.symbol, 0)
    if existing:
        logger.warning(
            "Reconciliation: broker already holds %d %s. The engine will not "
            "manage this position; flatten it manually or restart flat.",
            existing, strategy.symbol,
        )

    feed = IBKRFeed(broker.ib, strategy.symbol, bar_seconds=bar_seconds)
    risk = RiskManager(
        risk_fraction=settings.risk_fraction,
        max_portfolio_exposure=settings.max_portfolio_exposure,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        max_drawdown_pct=settings.max_drawdown_pct,
    )
    engine = Engine(
        feed=feed,
        strategy=strategy,
        risk=risk,
        broker=broker,
        portfolio=Portfolio(initial_cash=broker.equity()),
    )

    def request_stop(signum, frame) -> None:  # noqa: ARG001
        logger.info("Shutdown requested (signal %s)", signum)
        engine.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    timer: Optional[threading.Timer] = None
    if duration_minutes > 0:
        timer = threading.Timer(duration_minutes * 60, engine.stop)
        timer.daemon = True
        timer.start()
        logger.info("Session will end after %d minutes", duration_minutes)

    try:
        portfolio = engine.run()
    finally:
        if timer is not None:
            timer.cancel()
        broker.disconnect()

    reports = ReportGenerator(settings.report_dir)
    csv_path = reports.generate_csv(portfolio.fills, portfolio)
    html_path = reports.generate_html(portfolio.fills, portfolio)
    logger.info("Session reports: %s, %s", csv_path, html_path)
    return portfolio
