"""Centralised configuration loaded from the environment or a .env file.

Replaces the ad hoc os.getenv calls that were previously scattered across
bot.py and tradingview_service.py, so that every component reads the same
values and credentials never need to be passed on the command line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

from dotenv import load_dotenv

DEFAULT_SYMBOLS = ("SPY", "QQQ", "IWM")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.split("#")[0].strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None else float(raw.split("#")[0].strip())


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw.split("#")[0].strip())


@dataclass(frozen=True)
class StrategyConfig:
    fast: int = 20
    slow: int = 100
    atr_window: int = 14
    atr_stop_mult: float = 3.0
    risk_per_trade: float = 0.01
    max_weight: float = 0.5
    max_gross_exposure: float = 1.0


@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str = ""
    secret_key: str = ""
    paper: bool = True
    feed: str = "iex"

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)


@dataclass(frozen=True)
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    account: Optional[str] = None


@dataclass(frozen=True)
class Settings:
    broker: str = "alpaca"
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS
    history_days: int = 1500
    starting_equity: float = 100_000.0
    slippage_bps: float = 2.0
    commission_bps: float = 0.0
    min_order_notional: float = 50.0
    max_drawdown_stop: float = 0.20
    client_order_prefix: str = "boto"
    db_path: Optional[str] = "./trades.db"
    report_dir: str = "reports"
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)
    ibkr: IBKRConfig = field(default_factory=IBKRConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)

    @classmethod
    def from_env(cls, dotenv: bool = True) -> "Settings":
        if dotenv:
            load_dotenv()
        symbols = os.getenv("SYMBOLS", ",".join(DEFAULT_SYMBOLS))
        return cls(
            broker=os.getenv("BROKER", "alpaca").strip().lower(),
            symbols=tuple(s.strip().upper() for s in symbols.split(",") if s.strip()),
            history_days=_int("HISTORY_DAYS", 1500),
            starting_equity=_float("ACCOUNT_EQUITY", 100_000.0),
            slippage_bps=_float("SLIPPAGE_BPS", 2.0),
            commission_bps=_float("COMMISSION_BPS", 0.0),
            min_order_notional=_float("MIN_ORDER_NOTIONAL", 50.0),
            max_drawdown_stop=_float("MAX_DRAWDOWN_STOP", 0.20),
            db_path=os.getenv("DB_PATH") or None,
            report_dir=os.getenv("REPORT_DIR", "reports"),
            alpaca=AlpacaConfig(
                api_key=os.getenv("APCA_API_KEY_ID", ""),
                secret_key=os.getenv("APCA_API_SECRET_KEY", ""),
                paper=_bool("ALPACA_PAPER", True),
                feed=os.getenv("ALPACA_FEED", "iex").strip().lower(),
            ),
            ibkr=IBKRConfig(
                host=os.getenv("TWS_HOST", "127.0.0.1"),
                port=_int("TWS_PORT", 7497),
                client_id=_int("CLIENT_ID", 1),
                account=os.getenv("ACCOUNT") or None,
            ),
            strategy=StrategyConfig(
                fast=_int("SMA_FAST", 20),
                slow=_int("SMA_SLOW", 100),
                atr_window=_int("ATR_WINDOW", 14),
                atr_stop_mult=_float("ATR_STOP_MULT", 3.0),
                risk_per_trade=_float("RISK_PER_TRADE", 0.01),
                max_weight=_float("MAX_WEIGHT", 0.5),
                max_gross_exposure=_float("MAX_PORTFOLIO_EXPOSURE", 1.0),
            ),
        )

    def require_alpaca(self) -> AlpacaConfig:
        if not self.alpaca.configured:
            raise RuntimeError(
                "APCA_API_KEY_ID and APCA_API_SECRET_KEY must be set for Alpaca data or trading"
            )
        return self.alpaca
