"""TradingView (and generic) webhook receiver — advisory signal ingestion.

Mounted by ``agent/api_server.py`` via ``register_webhook_routes(app)``.

Design — this endpoint is deliberately **advisory-only**. It authenticates an
inbound TradingView alert against a pre-shared secret, records the signal, and
returns. It does **not** place orders. Order execution stays exclusively behind
the platform's mandate + order-guard path (``src/live/order_guard.py``); a
webhook that could place live orders directly is exactly the unguarded pattern
this project avoids. To act on a recorded signal, an authorized live runner with
a committed mandate reads it — the fail-closed guard still applies.

Auth model: TradingView alerts cannot send a bearer token, so the endpoint is
**not** behind ``require_auth``. Instead it validates a shared secret
(``TRADINGVIEW_WEBHOOK_SECRET``) with a constant-time compare, and fails closed
when the secret is unset. The secret may arrive either in the JSON body
(``{"secret": "..."}``) or as an ``X-Webhook-Secret`` header. Reading recent
signals (``GET /webhook/tradingview/signals``) *does* require the normal API auth.
"""

from __future__ import annotations

import datetime as _dt
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Request

logger = logging.getLogger(__name__)

_ALLOWED_ACTIONS = {"BUY", "SELL", "buy", "sell", "long", "short", "close", "flat"}
_MAX_BODY_BYTES = 64 * 1024  # a TradingView alert message is tiny; cap to be safe


def _signals_path() -> Path:
    """Resolve the JSONL path where inbound signals are appended.

    ``TRADINGVIEW_SIGNALS_PATH`` overrides; default is
    ``~/.vibe-trading/tradingview_signals.jsonl`` (user home, never the repo),
    matching the project's convention for runtime state.
    """
    from src.config.accessor import get_env_config

    override = get_env_config().api.tradingview_signals_path.strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".vibe-trading" / "tradingview_signals.jsonl"


def _append_signal(record: dict[str, Any]) -> None:
    """Append one signal record as a line of JSON, creating the dir if needed."""
    path = _signals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


AuthDep = Callable[..., Awaitable[Any] | Any]


def register_webhook_routes(app: FastAPI, require_auth: AuthDep | None = None) -> None:
    """Mount the webhook routes onto ``app``.

    Resolves ``require_auth`` from the host ``api_server`` module when not passed.
    """
    import sys as _sys

    if require_auth is None:
        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:
            raise RuntimeError(
                "register_webhook_routes: api_server not in sys.modules; import it first"
            )
        require_auth = host.require_auth

    @app.post("/webhook/tradingview")
    async def tradingview_webhook(request: Request) -> dict:
        """Receive a TradingView alert, authenticate it, and record the signal.

        Advisory only — never places an order. Fails closed when the secret is
        unset so an unconfigured endpoint can't be driven by anyone who reaches
        the port.
        """
        from src.config.accessor import get_env_config

        secret_cfg = get_env_config().api.tradingview_webhook_secret
        if not secret_cfg:
            raise HTTPException(
                status_code=503,
                detail="TRADINGVIEW_WEBHOOK_SECRET is not configured; refusing webhooks.",
            )

        raw = await request.body()
        if len(raw) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Payload too large")
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Payload must be a JSON object")

        # Secret from body or header; constant-time compare; fail closed.
        provided = data.get("secret")
        if not isinstance(provided, str):
            provided = request.headers.get("X-Webhook-Secret", "")
        if not hmac.compare_digest(provided, secret_cfg):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        symbol = data.get("symbol") or data.get("ticker")
        action = data.get("action") or data.get("side") or data.get("order_action")
        if action is not None and str(action) not in _ALLOWED_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"action must be one of {sorted(_ALLOWED_ACTIONS)}",
            )

        record = {
            "received_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "source": "tradingview",
            "symbol": str(symbol) if symbol is not None else None,
            "action": str(action) if action is not None else None,
            "quantity": data.get("quantity") or data.get("qty"),
            "price": data.get("price") or data.get("close"),
            "strategy": data.get("strategy") or data.get("alert_name"),
            # keep the raw alert (minus the secret) for downstream interpretation
            "raw": {k: v for k, v in data.items() if k != "secret"},
        }
        _append_signal(record)
        logger.info(
            "tradingview signal recorded: symbol=%s action=%s (advisory; no order placed)",
            record["symbol"],
            record["action"],
        )
        return {"status": "recorded", "advisory": True, "signal": record}

    @app.get("/webhook/tradingview/signals", dependencies=[Depends(require_auth)])
    async def tradingview_signals(limit: int = 50) -> dict:
        """Return the most recent recorded TradingView signals (newest first)."""
        path = _signals_path()
        if not path.exists():
            return {"status": "ok", "count": 0, "signals": []}
        limit = max(1, min(int(limit), 500))
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[dict] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # skip a corrupted line rather than failing the read
            if len(out) >= limit:
                break
        return {"status": "ok", "count": len(out), "signals": out}
