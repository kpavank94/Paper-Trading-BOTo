"""
Microservice for receiving TradingView webhook alerts and executing trades via
Interactive Brokers (IBKR).

This FastAPI application exposes a ``/webhook`` endpoint that accepts JSON
payloads from TradingView alerts.  The payload should include a ``secret``
matching the ``TRADINGVIEW_SECRET`` environment variable, along with the
``symbol``, ``action`` (``"BUY"`` or ``"SELL"``) and optional ``quantity``.

When a valid payload is received, the service connects to the IBKR API using
``ib_insync`` via our ``IBKRInterface`` class, submits a market order and
disconnects.  The default symbol and quantity can be specified in the
environment as ``DEFAULT_SYMBOL`` and ``DEFAULT_QUANTITY``.  Environment
variables are loaded from a ``.env`` file if present.

This microservice follows a microservices pattern: it is a standalone module
that can run independently of the main trading bot.  Credentials and
configuration values are read from environment variables rather than being
hard‑coded.
"""

from __future__ import annotations

import os
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

from .ibkr_interface import IBKRInterface, IBKRConnectionParams

# Load environment variables from .env file if present
load_dotenv()

app = FastAPI(title="TradingView Webhook Service", description="Receive TradingView alerts and place orders via IBKR")

# Secret used to authenticate incoming TradingView webhooks
TRADINGVIEW_SECRET = os.getenv("TRADINGVIEW_SECRET")



def get_ibkr_interface() -> IBKRInterface:
    """Create and return an IBKRInterface configured from environment variables."""
    params = IBKRConnectionParams(
        host=os.getenv("TWS_HOST", "127.0.0.1"),
        port=int(os.getenv("TWS_PORT", 7497)),
        client_id=int(os.getenv("CLIENT_ID", 1)),
        account=os.getenv("ACCOUNT"),
    )
    return IBKRInterface(params=params, db_path=os.getenv("DB_PATH"))


@app.post("/webhook")
async def tradingview_webhook(request: Request) -> dict:
    """Handle incoming webhook from TradingView or other services.

    The endpoint accepts JSON payloads containing order instructions.
    Fields:

    * ``secret`` – pre-shared secret token for authentication.
    * ``symbol`` – ticker symbol (e.g., ``"AAPL"``).  If omitted, ``DEFAULT_SYMBOL`` from the environment is used.
    * ``action`` – either ``"BUY"`` or ``"SELL"`` (case insensitive).
    * ``quantity`` – number of shares/contracts (optional, defaults to ``DEFAULT_QUANTITY`` in the environment).
    * ``order_type`` – ``"market"`` or ``"limit"`` (optional, defaults to ``"market"``).
    * ``limit_price`` – price for a limit order (required if ``order_type`` is ``"limit"``).

    Example payload:

    ```json
    {
        "secret": "mySecret",
        "symbol": "AAPL",
        "action": "BUY",
        "quantity": 5,
        "order_type": "limit",
        "limit_price": 150.25
    }
    ```

    If ``order_type`` is ``"market"`` or omitted, a market order is placed.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Validate secret
    secret = data.get("secret")
    if TRADINGVIEW_SECRET and secret != TRADINGVIEW_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    # Determine order parameters with fallbacks to environment variables
    symbol = data.get("symbol") or os.getenv("DEFAULT_SYMBOL")
    action = data.get("action")
    quantity = data.get("quantity") or os.getenv("DEFAULT_QUANTITY", 1)
    order_type = data.get("order_type") or os.getenv("DEFAULT_ORDER_TYPE", "market")
    limit_price = data.get("limit_price") or os.getenv("DEFAULT_LIMIT_PRICE")

    # Validate required fields
    if not symbol or not action:
        raise HTTPException(status_code=400, detail="Missing symbol or action")
    if str(action).upper() not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="Action must be 'BUY' or 'SELL'")
    if str(order_type).lower() not in {"market", "limit"}:
        raise HTTPException(status_code=400, detail="order_type must be 'market' or 'limit'")
    try:
        quantity = int(quantity)
    except Exception:
        raise HTTPException(status_code=400, detail="Quantity must be an integer")

    # Connect to IBKR and place the order accordingly
    ibkr = get_ibkr_interface()
    ibkr.connect()
    try:
        if str(order_type).lower() == "market":
            order_id = ibkr.place_market_order(symbol, quantity, str(action).upper())
        else:
            # limit order requires a price
            if limit_price is None:
                raise HTTPException(status_code=400, detail="limit_price is required for limit orders")
            try:
                price = float(limit_price)
            except Exception:
                raise HTTPException(status_code=400, detail="limit_price must be numeric")
            order_id = ibkr.place_limit_order(symbol, quantity, str(action).upper(), price)
    finally:
        ibkr.disconnect()

    return {"status": "success", "order_id": order_id}
