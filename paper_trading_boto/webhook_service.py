"""TradingView webhook service.

Security fixes over the original ``tradingview_service.py``:

* **Fail-closed**: the service refuses to handle requests when
  ``TRADINGVIEW_SECRET`` is unset.  The old code skipped auth entirely
  in that case, accepting orders from anyone.
* **HMAC authentication**: callers sign the raw request body with
  ``X-Signature: <hex(hmac_sha256(secret, body))>``.  A legacy in-body
  ``secret`` field is still accepted for TradingView alerts that cannot
  set headers, compared with ``hmac.compare_digest`` (constant-time).
* **Dedicated client id** (``WEBHOOK_CLIENT_ID``): the old service used
  the same id as the bot, so IBKR dropped one of the two connections.
* **Risk-managed orders**: entries are sized by the same
  :class:`RiskManager` as the bot and carry a broker-side stop, instead
  of firing raw market orders at whatever quantity the payload said.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import FastAPI, HTTPException, Request

from .broker.ibkr import IBKRBroker
from .config import Settings
from .events import OrderRequest, OrderType, Side, Signal, SignalAction, utcnow
from .risk import RiskManager

logger = logging.getLogger(__name__)

app = FastAPI(
    title="TradingView Webhook Service",
    description="Receive TradingView alerts and place risk-managed orders via IBKR",
)

settings = Settings.from_env()


def _verify_auth(body: bytes, signature_header: str | None, payload_secret: str | None) -> None:
    """Raise 401 unless the request authenticates. Fail closed on no secret."""
    secret = settings.tradingview_secret
    if not secret:
        # cli.py refuses to start without a secret; guard anyway in case
        # the app is mounted directly.
        raise HTTPException(status_code=503, detail="Service misconfigured: no secret set")
    if signature_header:
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature_header.strip().lower()):
            return
        raise HTTPException(status_code=401, detail="Invalid signature")
    if payload_secret is not None:
        if hmac.compare_digest(secret, str(payload_secret)):
            return
        raise HTTPException(status_code=401, detail="Invalid secret")
    raise HTTPException(status_code=401, detail="Missing X-Signature header or secret")


def _make_broker() -> IBKRBroker:
    return IBKRBroker(
        host=settings.tws_host,
        port=settings.tws_port,
        client_id=settings.webhook_client_id,  # never the bot's id
        account=settings.account,
    )


@app.post("/webhook")
async def tradingview_webhook(request: Request) -> dict:
    body = await request.body()
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    _verify_auth(body, request.headers.get("X-Signature"), data.get("secret"))

    symbol = data.get("symbol")
    action = str(data.get("action", "")).upper()
    if not symbol or action not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="symbol and action=BUY|SELL required")

    broker = _make_broker()
    broker.connect()
    try:
        price = broker.current_price(symbol)
        if price is None:
            raise HTTPException(status_code=502, detail=f"No market price for {symbol}")

        risk = RiskManager(
            risk_fraction=settings.risk_fraction,
            max_portfolio_exposure=settings.max_portfolio_exposure,
            stop_loss_pct=settings.stop_loss_pct,
            take_profit_pct=settings.take_profit_pct,
            max_drawdown_pct=settings.max_drawdown_pct,
        )
        position = broker.positions().get(symbol, 0)
        signal = Signal(
            symbol=symbol,
            action=SignalAction.ENTER_LONG if action == "BUY" else SignalAction.EXIT_LONG,
            timestamp=utcnow(),
            reason="tradingview-webhook",
        )
        order = risk.order_for_signal(
            signal, price=price, equity=broker.equity(), current_position=position
        )
        if order is None:
            return {"status": "rejected",
                    "detail": "risk layer produced no order (position/exposure/price)"}

        # Optional explicit limit price for entries.
        if data.get("order_type", "market").lower() == "limit":
            try:
                limit_price = float(data["limit_price"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=400,
                                    detail="numeric limit_price required for limit orders")
            order = OrderRequest(
                symbol=order.symbol, side=order.side, quantity=order.quantity,
                order_type=OrderType.LIMIT, limit_price=limit_price,
                stop_loss_price=order.stop_loss_price,
            )

        order_id = broker.submit_order(order)
        if order_id is None:
            raise HTTPException(status_code=502, detail="Order submission failed")
        logger.info("Webhook order %s: %s %d %s", order_id, order.side.value,
                    order.quantity, symbol)
        return {"status": "success", "order_id": order_id,
                "side": order.side.value, "quantity": order.quantity}
    finally:
        broker.disconnect()
