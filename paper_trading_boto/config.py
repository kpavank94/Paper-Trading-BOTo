"""Configuration loading for Paper Trading BOTo.

All runtime configuration comes from environment variables (optionally
via a ``.env`` file, loaded once here).  Keeping this in one dataclass
avoids the scattered ``os.getenv`` calls the original modules used and
makes defaults explicit and testable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    # IBKR connection
    tws_host: str = "127.0.0.1"
    tws_port: int = 7497  # paper port; live is 7496
    client_id: int = 1
    webhook_client_id: int = 2  # MUST differ from client_id: IBKR rejects duplicates
    account: Optional[str] = None

    # Logging / reporting
    db_path: Optional[str] = None
    report_dir: str = "reports"

    # Risk defaults
    risk_fraction: float = 0.05        # max fraction of equity per trade
    max_portfolio_exposure: float = 0.2
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    max_drawdown_pct: float = 0.25     # kill-switch: halt trading past this drawdown

    # Webhook
    tradingview_secret: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        def _opt(name: str) -> Optional[str]:
            value = os.getenv(name)
            return value if value else None

        return cls(
            tws_host=os.getenv("TWS_HOST", cls.tws_host),
            tws_port=int(os.getenv("TWS_PORT", cls.tws_port)),
            client_id=int(os.getenv("CLIENT_ID", cls.client_id)),
            webhook_client_id=int(os.getenv("WEBHOOK_CLIENT_ID", cls.webhook_client_id)),
            account=_opt("ACCOUNT"),
            db_path=_opt("DB_PATH"),
            report_dir=os.getenv("REPORT_DIR", cls.report_dir),
            risk_fraction=float(os.getenv("RISK_FRACTION", cls.risk_fraction)),
            max_portfolio_exposure=float(
                os.getenv("MAX_PORTFOLIO_EXPOSURE", cls.max_portfolio_exposure)
            ),
            stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", cls.stop_loss_pct)),
            take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", cls.take_profit_pct)),
            max_drawdown_pct=float(os.getenv("MAX_DRAWDOWN_PCT", cls.max_drawdown_pct)),
            tradingview_secret=_opt("TRADINGVIEW_SECRET"),
        )
