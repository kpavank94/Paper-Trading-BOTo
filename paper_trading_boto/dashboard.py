#!/usr/bin/env python3
"""
Streamlit dashboard for Paper Trading BOTo.

This module exposes a simple web UI to interact with the bot
through the browser.  Beginners can connect to their Interactive
Brokers paper account, view account summary, submit manual orders,
and experiment with a basic SMA crossover strategy without writing
any code.  Configuration values such as host, port and default
trading parameters are loaded from environment variables or the
.env file.

Features
--------

* Connect/disconnect to the IBKR API with a click.
* Submit market and limit orders for any stock symbol.
* View a basic account summary (cash, equity, margin) pulled from IBKR.
* Run a short session of the SMA crossover strategy on a chosen symbol.

The goal of this dashboard is to provide a friendly starting point
for novice traders to explore algorithmic trading concepts.  It is
not intended for production use and omits many advanced features such
as persistent state management, asynchronous execution and robust
error handling.  See the README for additional guidance.
"""

from __future__ import annotations

import datetime
import os
import time

import streamlit as st
from dotenv import load_dotenv

from .ibkr_interface import IBKRInterface, IBKRConnectionParams
from .risk_management import FixedFractionalRiskManager
from .strategy import SMACrossoverStrategy
from .cost_basis import CostBasisTracker, TradeRecord


# Load environment variables from .env if present
load_dotenv()


def init_session_state() -> None:
    """Initialize Streamlit session state variables."""
    if "ibkr" not in st.session_state:
        st.session_state.ibkr = None
    if "cost_tracker" not in st.session_state:
        st.session_state.cost_tracker = None


def connect_ibkr(host: str, port: int, client_id: int, account: str | None) -> IBKRInterface:
    """Instantiate and connect an IBKRInterface, saving it in session state."""
    params = IBKRConnectionParams(host=host, port=port, client_id=client_id, account=account or None)
    ibkr = IBKRInterface(params=params, db_path=os.getenv("DB_PATH"))
    ibkr.connect()
    st.session_state.ibkr = ibkr
    st.session_state.cost_tracker = CostBasisTracker()
    return ibkr


def disconnect_ibkr() -> None:
    """Disconnect from IBKR and clear session state."""
    ibkr: IBKRInterface | None = st.session_state.get("ibkr")
    if ibkr:
        ibkr.disconnect()
    st.session_state.ibkr = None
    st.session_state.cost_tracker = None


def main() -> None:
    st.set_page_config(page_title="Paper Trading BOTo", layout="wide")
    init_session_state()

    st.title("\U0001F4C8 Paper Trading BOTo Dashboard")
    st.write(
        "Use this dashboard to connect to your IBKR paper account, place trades, "
        "monitor your account and experiment with a simple SMA crossover strategy."
    )

    # Sidebar for connection settings
    with st.sidebar:
        st.header("Connection Settings")
        default_host = os.getenv("TWS_HOST", "127.0.0.1")
        default_port = int(os.getenv("TWS_PORT", 7497))
        default_client_id = int(os.getenv("CLIENT_ID", 1))
        default_account = os.getenv("ACCOUNT", "")

        host = st.text_input("Host", value=default_host)
        port = st.number_input("Port", value=default_port, step=1)
        client_id = st.number_input("Client ID", value=default_client_id, step=1)
        account = st.text_input("Account (optional)", value=default_account)

        if st.session_state.ibkr:
            if st.button("Disconnect"):
                disconnect_ibkr()
                st.success("Disconnected from IBKR")
        else:
            if st.button("Connect"):
                try:
                    connect_ibkr(host, int(port), int(client_id), account or None)
                    st.success("Connected to IBKR")
                except Exception as exc:
                    st.error(f"Failed to connect: {exc}")

    # Only show trading controls if connected
    if st.session_state.ibkr:
        ibkr = st.session_state.ibkr
        cost_tracker: CostBasisTracker = st.session_state.cost_tracker
        st.subheader("Manual Trading")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            symbol = st.text_input("Symbol", value=os.getenv("DEFAULT_SYMBOL", "AAPL"))
        with col2:
            quantity = st.number_input(
                "Quantity", min_value=1, value=int(os.getenv("DEFAULT_QUANTITY", 10)), step=1
            )
        with col3:
            action = st.selectbox("Action", options=["BUY", "SELL"])
        with col4:
            order_type = st.selectbox("Order Type", options=["Market", "Limit"])
        limit_price = None
        if order_type.lower() == "limit":
            limit_price = st.number_input(
                "Limit Price",
                value=float(os.getenv("DEFAULT_LIMIT_PRICE", "0.0") or 0.0),
                min_value=0.0,
                step=0.01,
            )
        if st.button("Place Order"):
            try:
                if order_type.lower() == "market":
                    ibkr.place_market_order(symbol, int(quantity), action)
                    st.success(f"Market order submitted: {action} {quantity} {symbol}")
                else:
                    if limit_price is None or limit_price <= 0:
                        st.warning("Please enter a valid limit price")
                    else:
                        ibkr.place_limit_order(symbol, int(quantity), action, float(limit_price))
                        st.success(
                            f"Limit order submitted: {action} {quantity} {symbol} at {limit_price:.2f}"
                        )
            except Exception as exc:
                st.error(f"Failed to place order: {exc}")

        # Display account summary
        st.subheader("Account Summary")
        if st.button("Refresh Summary"):
            summy = ibkr.get_account_summary()
            if summary:
                st.json(summary)
            else:
                st.info("No account summary available (ensure ACCOUNT is set in your .env)")

        # SMA strategy section
        st.subheader("Run SMA Crossover Strategy")
        sma_col1, sma_col2, sma_col3, sma_col4 = st.columns(4)
        with sma_col1:
            sma_symbol = st.text_input(
                "Strategy Symbol", value=os.getenv("DEFAULT_SYMBOL", "AAPL"), key="sma_symbol"
            )
        with sma_col2:
            short_window = st.number_input("Short Window", min_value=1, value=10, step=1)
        with sma_col3:
            long_window = st.number_input("Long Window", min_value=2, value=30, step=1)
        with sma_col4:
            sma_quantity = st.number_input("Strategy Quantity", min_value=1, value=10, step=1)
        duration_minutes = st.number_input("Session Duration (minutes)", min_value=1, value=1, step=1)

        if st.button("Start SMA Session"):
            # Use a simple loop with limited iterations for demonstration
            st.info(
                "Running SMA crossover strategy session. This will take a few moments..."
            )
            risk_manager = FixedFractionalRiskManager(max_fraction=0.05, account_value=10000.0)
            strategy = SMACrossoverStrategy(
                ibkr=ibkr,
                symbol=sma_symbol,
                quantity=int(sma_quantity),
                risk_manager=risk_manager,
                cost_tracker=cost_tracker,
                short_window=int(short_window),
                long_window=int(long_window),
            )
            strategy.on_start()
            start_time = datetime.datetime.utcnow()
            end_time = start_time + datetime.timedelta(minutes=int(duration_minutes))
            try:
                while datetime.datetime.utcnow() < end_time:
                    current_price = ibkr.get_current_price(sma_symbol)
                    now = datetime.datetime.utcnow()
                    if current_price is not None:
                        strategy.on_tick(current_price, now)
                    # check exit conditions (risk manager)
                    if (
                        strategy.position != 0
                        and risk_manager.should_exit_position(
                            entry_price=strategy.entry_price or current_price,
                            current_price=current_price or 0.0,
                            position=strategy.position,
                        )
                    ):
                        exit_action = "SELL" if strategy.position > 0 else "BUY"
                        qty = abs(strategy.position)
                        ibkr.place_market_order(sma_symbol, qty, exit_action)
                        cost_tracker.record_trade(
                            TradeRecord(
                                symbol=sma_symbol,
                                action=exit_action,
                                quantity=qty,
                                price=current_price if current_price is not None else 0.0,
                                timestamp=now,
                            )
                        )
                        strategy.position = 0
                        strategy.entry_price = None
                    time.sleep(2)
                strategy.on_finish()
                st.success("SMA session completed")
            except Exception as exc:
                st.error(f"Error during strategy session: {exc}")

        # Display cost basis / trade history
        st.subheader("Trade History")
        if cost_tracker and cost_tracker.trade_history:
            st.write(cost_tracker.trade_history)
        else:
            st.info("No trades have been recorded yet.")
    else:
        st.info("Connect to IBKR via the sidebar to start trading.")


if __name__ == "__main__":
    main()
