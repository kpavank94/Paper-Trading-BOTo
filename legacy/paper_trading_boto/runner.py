"""Daily rebalance loop.

Replaces the fixed interval polling loop that used to live in bot.py. Two
problems with that loop are fixed here: it sampled prices every few seconds
but treated them as bars, and it slept through the market close without
knowing whether the session was open at all.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Dict, List, Optional, Tuple

from .brokers import Broker, Intent, build_broker, plan_orders
from .config import Settings
from .cost_basis import CostBasisTracker, TradeRecord
from .data import MarketData
from .reporting import ReportGenerator
from .risk_management import PortfolioRiskManager
from .strategy import BaseStrategy, SMACrossoverStrategy

log = logging.getLogger(__name__)


def build_strategy(settings: Settings) -> SMACrossoverStrategy:
    cfg = settings.strategy
    return SMACrossoverStrategy(
        fast=cfg.fast,
        slow=cfg.slow,
        atr_window=cfg.atr_window,
        atr_stop_mult=cfg.atr_stop_mult,
        risk_per_trade=cfg.risk_per_trade,
        max_weight=cfg.max_weight,
    )


class Runner:
    def __init__(
        self,
        settings: Settings,
        strategy: Optional[BaseStrategy] = None,
        broker: Optional[Broker] = None,
    ) -> None:
        self.settings = settings
        self.strategy = strategy or build_strategy(settings)
        self.broker = broker or build_broker(settings)
        self.data = MarketData(settings)
        self.cost_tracker = CostBasisTracker()
        self.risk = PortfolioRiskManager(
            max_gross_exposure=settings.strategy.max_gross_exposure,
            max_weight=settings.strategy.max_weight,
            max_drawdown_stop=settings.max_drawdown_stop,
        )

    def latest_targets(self) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Weights and reference prices from the most recent completed bar."""
        from .strategy import portfolio_targets

        lookback = max(self.strategy.warmup * 3, 400)
        bars = self.data.daily_bars(lookback_days=lookback)
        panel = portfolio_targets(
            self.strategy, bars, self.settings.strategy.max_gross_exposure
        )
        if panel.empty:
            return {}, {}
        return panel.iloc[-1].to_dict(), self.data.last_prices(bars)

    def rebalance(self, dry_run: bool = True) -> List[Intent]:
        if not self.broker.market_is_open():
            log.info("market is closed, no action taken")
            return []

        equity = self.broker.equity()
        if self.risk.update_equity(equity):
            log.error(
                "drawdown %.1f%% breached the %.1f%% limit, flattening and halting",
                self.risk.drawdown * 100,
                self.settings.max_drawdown_stop * 100,
            )
            if not dry_run:
                self.broker.flatten()
            return []

        weights, prices = self.latest_targets()
        if not weights:
            log.warning("no targets produced, check symbols and warmup length")
            return []

        weights = self.risk.apply(weights)
        log.info(
            "equity=%.2f targets=%s", equity, {k: round(v, 4) for k, v in weights.items()}
        )

        intents = plan_orders(
            target_weights=weights,
            prices=prices,
            equity=equity,
            held=self.broker.positions(),
            min_notional=self.settings.min_order_notional,
            blocked=set(self.broker.working_symbols()),
        )
        if not intents:
            log.info("book already matches targets")
            return []

        for intent in intents:
            log.info(
                "%s %s %s shares (%.2f USD)",
                "DRY" if dry_run else "SEND",
                intent.action,
                intent.quantity,
                intent.notional,
            )
            if dry_run:
                continue
            order_id = self.broker.submit_market_order(
                intent.symbol, intent.quantity, intent.action
            )
            if order_id:
                self.cost_tracker.record_trade(
                    TradeRecord(
                        symbol=intent.symbol,
                        action=intent.action,
                        quantity=intent.quantity,
                        price=prices[intent.symbol],
                        timestamp=dt.datetime.now(dt.timezone.utc),
                    )
                )
        return intents

    def report(self) -> Optional[str]:
        if not self.cost_tracker.trade_history:
            return None
        generator = ReportGenerator(output_dir=self.settings.report_dir)
        csv_path = generator.generate_csv(self.cost_tracker.trade_history, self.cost_tracker)
        generator.generate_html(self.cost_tracker.trade_history, self.cost_tracker)
        return csv_path

    def loop(self, minutes_before_close: int = 15, dry_run: bool = True) -> None:
        """Wake shortly before each close, rebalance once, then sleep again.

        Trading near the close means the signal is computed from a nearly
        complete bar, which keeps live behaviour close to the backtest.
        """
        self.broker.connect()
        try:
            while True:
                if self.risk.halted:
                    log.error("risk halt active, exiting loop")
                    return
                wait = self._sleep_seconds(minutes_before_close, dry_run)
                log.info("sleeping %.0f seconds", wait)
                time.sleep(min(wait, 3600))
        except KeyboardInterrupt:
            log.info("interrupted by user")
        finally:
            path = self.report()
            if path:
                log.info("session report written to %s", path)
            self.broker.disconnect()

    def _sleep_seconds(self, minutes_before_close: int, dry_run: bool) -> float:
        clock = getattr(self.broker, "client", None)
        now = dt.datetime.now(dt.timezone.utc)
        if clock is None or not hasattr(clock, "get_clock"):
            self.rebalance(dry_run=dry_run)
            return 3600.0

        state = clock.get_clock()
        trigger = state.next_close - dt.timedelta(minutes=minutes_before_close)
        if state.is_open and now >= trigger:
            self.rebalance(dry_run=dry_run)
            return max((state.next_close - now).total_seconds() + 60, 60)
        target = trigger if state.is_open else state.next_open
        return max((target - now).total_seconds(), 30)
