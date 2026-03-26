# Usage Guide

This document explains how to set up, run and test **Paper Trading BOTo**. Before running any code, please ensure that you have read through the [Overview](overview.md) for context.

## Prerequisites

- [Python 3.10+](https://www.python.org/) installed on your system.
- An Interactive Brokers TWS or IB Gateway running with API access enabled (paper trading recommended).
- Access to your IBKR account number and port.
- Basic familiarity with using the command line.

## Installation

1. Clone the repository and create a virtual environment:

   ```sh
   git clone https://github.com/your-username/paper-trading-boto.git
   cd paper-trading-boto
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies from the root `requirements.txt`:

   ```sh
   pip install -r requirements.txt
   ```

3. Copy the example environment file and edit it:

   ```sh
   cp .env.example .env
   # open .env in your favourite editor and set TWS_HOST, TWS_PORT, CLIENT_ID, ACCOUNT, DB_PATH, RISK parameters, etc.
   ```

   Use `TRADINGVIEW_SECRET` and related variables to configure the TradingView webhook microservice, and set the defaults for the Streamlit dashboard (symbol, quantity, order type, limit price).

## Running the CLI bot

The `paper_trading_boto.bot` module provides a command-line interface to run an SMA crossover strategy and produce reports.

```sh
python -m paper_trading_boto.bot --symbol AAPL --short-window 20 --long-window 50 --quantity 10 --duration-minutes 30
```

This will connect to IBKR using your `.env` configuration, run the strategy for 30 minutes, log trades and generate CSV/HTML reports.

## Running the TradingView webhook service

The FastAPI microservice in `paper_trading_boto/tradingview_service.py` allows you to receive webhook alerts from TradingView or other platforms and execute trades automatically. To run the service:

```sh
uvicorn paper_trading_boto.tradingview_service:app --host 0.0.0.0 --port 8000
```

Configure TradingView alerts to post JSON payloads (with fields `secret`, `symbol`, `action`, `quantity`, `order_type`, `limit_price`) to `http://your-server:8000/webhook`. The `secret` must match `TRADINGVIEW_SECRET` in your `.env` file.

## Running the Streamlit dashboard

The dashboard provides an interactive web UI for beginners to connect to IBKR, place manual orders, run a simple SMA strategy, load a TradingView strategy URL and view account summaries and trade history.

Start it with:

```sh
streamlit run paper_trading_boto/dashboard.py
```

Open the URL shown in your terminal (usually `http://localhost:8501`) in a browser. Use the sidebar to configure connection parameters, place trades, run strategies, or paste a TradingView strategy URL (a JSON feed or webhook). The dashboard will display live status updates and trade history.

## Running unit tests

The `tests/` directory contains comprehensive unit tests for the bot interfaces, risk management, cost basis tracking, strategies, webhook service and dashboard helper functions.

To run the tests, install `pytest` and `requests` (already listed in `requirements.txt`) and execute:

```sh
pytest -q
```

Test coverage ensures that connections, order execution, risk constraints and cost basis calculations behave as expected. Running the tests before trading is highly recommended to catch configuration or implementation errors.

---

For additional details, refer to the [FAQ](FAQ.md) or explore the original module documentation in the `paper_trading_boto/` package.
