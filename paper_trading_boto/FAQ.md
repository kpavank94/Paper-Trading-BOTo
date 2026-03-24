# Frequently Asked Questions (FAQ)

This FAQ summarises common questions about building algorithmic trading bots for Interactive Brokers (IBKR) and highlights lessons learned from other open‑source projects.  It is divided into functional topics with references to specific commits and documentation lines.

## 1. Why does BOTo use `ib_insync` instead of the official `ibapi`?

The official `ibapi` library is powerful but verbose.  `ib_insync` wraps the `ibapi` client in a synchronous interface, simplifying connection management and order handling.  Several open‑source projects adopt `ib_insync` for this reason.  For example, the *trading‑bot‑framework* rewrote its IBKR trader using a synchronous approach based on `ib_async` and added unified logging for easier debugging【730412866638135†L82-L90】.

## 2. How should I manage configuration and credentials?

Configuration should be externalised to avoid hard‑coding sensitive information.  A common practice is to use a `.env` file with variables such as `TWS_HOST`, `TWS_PORT`, `CLIENT_ID`, and `ACCOUNT`.  The `ibkr_trading_app` repository completely restructured itself to incorporate environment variable management and secure email credentials handling【797224965603579†L78-L88】.  BOTo includes a `.env.example` file that you can copy to `.env` and customise.

## 3. What logging and monitoring options exist?

Robust logging is critical for diagnosing issues.  Several projects implemented database logging and monitoring:

* *trading‑bot‑framework* added comprehensive PostgreSQL logging and Grafana dashboards in a large commit【6889114618198†L82-L90】.  It also introduced auto‑detection of database availability【735478255617264†L82-L89】, ensuring the bot continues to operate even if the database is unavailable.
* *ibkr_trading_app* added email reporting with attachments and market‑closed exit options【157485389729687†L78-L83】【634560943035447†L147-L240】.

BOTo uses Python’s built‑in `logging` module to record events.  If a `DB_PATH` is specified in the `.env` file, logs and trades are also persisted to a local SQLite database.  Reports are generated after each session in both CSV and optional HTML formats.

## 4. How does BOTo handle risk management?

Risk management features were inspired by multiple repositories:

* *quantum‑trader* implements a risk management system with position limits, daily loss limits, drawdown protection and trade frequency controls【362023408974584†L165-L196】.
* *ibkr_trading_app* maintains a 50 % cash reserve and checks price reasonability before submitting orders【560845306289458†L185-L206】.

BOTo includes configurable position sizing, maximum portfolio exposure, stop‑loss and take‑profit thresholds.  These parameters can be set through command‑line arguments or environment variables.  The default risk manager calculates position size as a fixed quantity, but you can implement your own sizing logic in `risk_management.py`.

## 5. What is cost basis analysis and why is it important?

Cost basis analysis tracks the average price paid for a position, enabling accurate calculation of both realized and unrealized profit/loss.  This is essential for evaluating strategy performance and for tax reporting.  BOTo maintains a ledger of trades and updates the cost basis each time shares are bought or sold.  A summary of cost basis and PnL is included in the generated report.

## 6. Can I connect BOTo to a live IBKR account?

Yes, but the default configuration uses paper trading.  To connect to a live account, set the `TWS_PORT` to the live trading port (usually `7496`) and ensure that the account number corresponds to your live account.  **Important:** modify and test your strategy thoroughly on paper trading before switching to a live environment.  Always abide by IBKR’s API rules and the risk constraints that you set.

## 7. How do I create my own strategy?

Strategies inherit from the `BaseStrategy` class in `strategy.py` and must implement at least two methods: `on_tick()` and `on_start()`.  The `on_tick()` method receives real‑time bars and decides whether to enter or exit positions.  For example, the sample SMA crossover strategy buys when a short‑term moving average crosses above a long‑term average and sells when the opposite occurs.  The risk manager ensures that orders respect position limits.

## 8. Why does BOTo support generating HTML reports?

The `ibkr_trading_app` project demonstrates the value of rich reporting—its commits added HTML email templates, file attachments and summarised trading records【157485389729687†L78-L83】【138109514620491†L76-L81】.  HTML reports make it easier to visualise results and integrate with email notifications or dashboards.  BOTo includes a simple HTML report generator in `reporting.py` that you can customise or extend.

## 9. What are some common pitfalls when using the IBKR API?

Based on issues encountered in other projects:

1. **Read‑only API:** Ensure that the IBKR TWS/Gateway option “Read‑Only API” is disabled; otherwise orders cannot be placed【560845306289458†L275-L294】.
2. **Port configuration:** The default ports for paper and live trading are different (7497 vs 7496).  Setting the wrong port will result in connection errors.
3. **Historical data limits:** IBKR imposes strict rate limits on historical data requests.  The *trading‑bot‑framework* fixed historical data timeouts by adjusting duration calculation and qualifying contracts properly【259634449855701†L83-L92】.  When fetching large amounts of data, throttle requests and handle exceptions gracefully.
4. **Market hours:** The IBKR API does not allow trading outside market hours for many instruments.  A commit in `ibkr_trading_app` added a market‑closed exit option that prompts the user to wait or exit【634560943035447†L146-L240】.  BOTo checks the market status before submitting orders and waits until the market is open.

## 10. Is this bot guaranteed to be profitable?

No.  Algorithmic trading involves uncertainty, and no system can guarantee profits.  BOTo provides a framework to explore strategies and implement sound risk management.  Its design draws on best practices from multiple open‑source projects, but success ultimately depends on your strategy logic, risk tolerance and market conditions.  Always perform your own research and backtesting.