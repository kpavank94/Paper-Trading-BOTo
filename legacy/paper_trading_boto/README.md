# Paper Trading BOTo

**Paper Trading BOTo** is a Python‑based algorithmic trading framework that connects to an Interactive Brokers paper trading account via the `ib_insync` API.  It was inspired by several open‑source IBKR trading projects and includes features gleaned from their commit histories, such as robust logging, database support, risk management, and easy extensibility.  The goal of BOTo is to provide a clear starting point for building, testing and analysing trading strategies in a paper environment before committing real capital.

## Why build this?

Open‑source IBKR trading projects illustrate how a simple strategy often grows into a complex system with features such as database logging, monitoring, email reporting and error handling.  For example, the **trading‑bot‑framework** repository added asynchronous PostgreSQL logging and improved historical data retrieval in a series of commits【735478255617264†L82-L89】【259634449855701†L83-L92】.  The **ibkr_trading_app** project evolved from a basic SPX strategy into a fully fledged application with environment configuration, email reporting and improved connection reliability【560845306289458†L185-L206】【157485389729687†L78-L83】.  By examining these histories we learned that:

* **Clear configuration and environment management** avoid accidental exposure of credentials.  The `trading‑bot‑framework` introduced a `.env.example` and automatic detection of PostgreSQL availability【6889114618198†L82-L90】【735478255617264†L82-L89】, while `ibkr_trading_app` restructured its project around an `.env` file and environment loader【797224965603579†L78-L88】.
* **Database and logging support** enable analysis and troubleshooting.  Commits added a comprehensive database schema, Grafana dashboards and unified logging across traders【6889114618198†L82-L90】.  Unified logging also simplifies debugging of asynchronous IBKR connections【730412866638135†L82-L90】.
* **Risk management and cost tracking** are essential.  Projects such as `quantum‑trader` provide risk limits, position sizing and drawdown protection【362023408974584†L165-L196】, while `ibkr_trading_app` enforces a 50 % cash reserve and price reasonability checks【560845306289458†L185-L206】.
* **User‑friendly reports and notifications** help traders monitor performance.  Commits in `ibkr_trading_app` added email summaries with attachments and market‑closed options to exit gracefully【157485389729687†L78-L83】【634560943035447†L147-L240】.

BOTo incorporates these lessons by providing a clean codebase with modular components, cost basis analysis and an extensible strategy interface.  The aim is not to provide a “holy‑grail” algorithm but to create a sandbox where you can safely develop and refine your ideas.

## Features

* **Two brokers behind one interface:**  Alpaca (default) and IBKR both implement the same `Broker` protocol, so strategy code never imports a vendor SDK. Switch with `BROKER=alpaca` or `BROKER=ibkr`; `ib_insync` is only imported when IBKR is selected.
* **Bar driven strategy framework:**  Subclass `BaseStrategy` and implement `evaluate()`, which returns a *target weight* per bar instead of firing orders directly. The same code path drives the backtester and the live runner, so a backtest tests what actually trades.
* **Backtesting with a realistic fill model:**  Signals formed at a bar's close are filled at the next bar's open, and the overnight gap is attributed to the weight held before that fill. Costs are charged on turnover. Metrics reported: CAGR, annualised volatility, Sharpe, maximum drawdown, Calmar, average gross exposure, annualised turnover and hit rate.
* **Volatility scaled sizing:**  Positions are sized so that an adverse move of N average true ranges costs a fixed fraction of equity, so a quiet symbol receives a larger allocation than a volatile one for the same risk budget.
* **Portfolio risk guards:**  A gross exposure ceiling, a per symbol weight ceiling, and a drawdown kill switch that flattens the book and blocks new entries.
* **Order reconciliation:**  The live runner diffs target weights against the actual book, skips symbols that already have a working order, ignores sub minimum dust, and closes holdings that are no longer targeted.
* **Cost basis analysis:**  BOTo tracks the average cost of open positions and computes realized and unrealized PnL.
* **Logging & optional database support:**  Transactions, orders and account balances are logged to standard output and optionally to a local SQLite database. If the database connection fails, logging continues to the console.
* **Reports:**  After each trading session the bot generates CSV and HTML reports summarising trades, positions, cost basis and PnL.
* **Tests:**  A pytest suite covers signal correctness (including an explicit no lookahead check), the backtest accounting identities, and the order planning rules. It runs offline against synthetic bars.

## Installation

### 1 – Prerequisites

1. **Interactive Brokers account:** Sign up for an IBKR account.  Paper trading requires enabling API access and disabling the “Read‑Only API” option in TWS or IB Gateway (see the IBKR documentation).
2. **Python ≥3.9** and `pip` installed on your machine.
3. **TWS or IB Gateway:** Download and install the Trader Workstation or Gateway, enable “ActiveX and Socket Clients” and note the paper trading port (default `7497`)【560845306289458†L275-L294】.

### 2 – Clone and install dependencies

```sh
git clone https://github.com/your‑username/paper‑trading‑boto.git
cd paper‑trading‑boto
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3 – Configuration

Copy the provided `.env.example` to `.env` and set your configuration variables:

```sh
cp .env.example .env
```

The most important variables are:

* `TWS_HOST`: host for TWS/Gateway (default `127.0.0.1`)
* `TWS_PORT`: paper trading port (default `7497`)
* `CLIENT_ID`: any integer (use a unique value per application)
* `ACCOUNT`: your IBKR paper account number (optional)
* `DB_PATH`: path to an SQLite database file for logging (optional)

### 4 - Running the bot

Everything runs through one entry point. Credentials come from `.env`, so no secret is ever passed as a command line argument.

Evaluate the strategy on history before risking anything:

```sh
python -m paper_trading_boto.bot backtest --symbols SPY,QQQ,IWM --out equity.csv
```

Dry run a single rebalance. Intended orders are logged and nothing is sent:

```sh
python -m paper_trading_boto.bot once
```

Send orders to the configured paper account, once or continuously:

```sh
python -m paper_trading_boto.bot once --live
python -m paper_trading_boto.bot loop --live
```

Close every open position:

```sh
python -m paper_trading_boto.bot flatten
```

`loop` wakes shortly before each close, rebalances against a nearly complete bar, then sleeps until the next session. Strategy parameters can be overridden per run with `--fast`, `--slow`, `--atr-stop-mult` and `--risk-per-trade`. At the end of a session the bot writes CSV and HTML reports to the `reports/` directory.

Run the tests with:

```sh
python -m pytest paper_trading_boto/tests -q
```

## Project structure

```
paper_trading_boto/
├── bot.py                # CLI: backtest, once, loop, flatten
├── config.py             # Typed settings loaded from .env
├── data.py               # Daily OHLCV bars from the Alpaca market data API
├── strategy.py           # BaseStrategy, SMACrossoverStrategy, portfolio_targets
├── backtest.py           # Backtest engine and performance metrics
├── runner.py             # Live rebalance loop and session reporting
├── risk_management.py    # Portfolio guards and legacy per trade sizing
├── brokers/              # Broker protocol plus Alpaca and IBKR adapters
├── ibkr_interface.py     # ib_insync connection wrapper and API helpers
├── cost_basis.py         # Classes for tracking cost basis and PnL
├── reporting.py          # Report generation (CSV and HTML)
├── tradingview_service.py # Optional FastAPI webhook receiver
├── tests/                # Offline pytest suite
├── utils/logging_config.py # Logging configuration
├── .env.example          # Example environment configuration file
├── requirements.txt      # Python dependencies
├── README.md             # This documentation
└── FAQ.md                # Frequently asked questions and lessons learned
```

## Disclaimer

This software is for educational purposes only.  Algorithmic trading carries significant financial risk.  Always test strategies thoroughly in a paper trading environment and consult with a financial professional before live deployment.  The authors do not assume responsibility for losses incurred.