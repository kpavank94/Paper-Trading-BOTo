# Paper Trading BOTo

An event-driven paper trading bot. The same strategy code runs in two modes:

- **Backtest** — historical bars from yfinance (or a local CSV) against a
  simulated broker with next-bar-open fills, slippage and commissions.
- **Live paper** — streaming bars from Interactive Brokers (TWS / IB Gateway
  paper account) via [`ib_async`](https://github.com/ib-api-reloaded/ib_async),
  with fill-confirmed positions and broker-side protective stops.

## Architecture

```
DataFeed (bars) ──> Engine ──> Strategy.on_bar() ──> Signal
                      │                                │
                      v                                v
                 fills ──> Portfolio            RiskManager (sizing, stops,
                      ^                          exposure cap, kill-switch)
                      │                                │
                 Broker interface  <───── OrderRequest ┘
                 ├── SimulatedBroker   (backtest)
                 └── IBKRBroker        (live paper)
```

Design rules:

- **Strategies are pure signal generators.** They see `Bar`s and return
  `Signal`s. No broker handle, no sizing, no cash.
- **Positions derive from confirmed fills only.** Nothing updates state
  because an order was merely submitted.
- **Stops live broker-side.** An entry carries its stop price; the IBKR
  adapter transmits parent + stop atomically, so protection survives the
  bot process dying. The engine's stop/take-profit check is a backstop.
- **A missing price is no information.** Failed market data fetches can
  never trigger an exit.

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Backtest

```sh
boto backtest --symbol AAPL --start 2024-01-01 --end 2025-01-01 \
     --strategy sma_crossover --short-window 10 --long-window 30
```

Prints total return, max drawdown, Sharpe, win rate and trade counts, and
writes an HTML report to `reports/`.

## Live paper trading

1. Run TWS or IB Gateway with a **paper** account, API enabled
   ("ActiveX and Socket Clients", read-only API off), port 7497.
2. `cp paper_trading_boto/.env.example .env` and fill in connection values.
3. ```sh
   boto live --symbol AAPL --strategy sma_crossover --bar-seconds 60
   ```

The bot warms the strategy up from historical bars, streams real-time bars,
reconciles existing broker positions at startup (it warns and leaves them
alone), and writes a session report on exit (Ctrl-C or `--duration N` minutes).

## TradingView webhook service

```sh
boto webhook --port 8000
```

Requires `TRADINGVIEW_SECRET` — the service refuses to start without it.
Requests are authenticated with an HMAC signature over the raw body:

```sh
BODY='{"symbol":"AAPL","action":"BUY"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$TRADINGVIEW_SECRET" | awk '{print $2}')
curl -s -X POST localhost:8000/webhook -H "Content-Type: application/json" \
     -H "X-Signature: $SIG" -d "$BODY"
```

(A legacy in-body `"secret"` field is accepted for TradingView alerts that
cannot set headers.) Orders are sized by the same risk layer as the bot —
the payload cannot choose its own quantity — and entries carry a stop.

## Tests

```sh
pytest
```

The suite (portfolio accounting, simulated broker, strategy signals, risk
rules, end-to-end backtest on a fixture CSV, webhook auth) needs no network
and no IBKR connection.

## Strategy development

Subclass `Strategy` (`paper_trading_boto/strategy/base.py`):

```python
class MyStrategy(Strategy):
    def warmup_bars(self) -> int: ...          # history needed before first signal
    def on_start(self, history: list[Bar]): ...  # consume warmup bars
    def on_bar(self, bar: Bar) -> Signal | None: ...
```

Register it in `STRATEGIES` (`paper_trading_boto/strategy/__init__.py`) and it
becomes available to both `boto backtest` and `boto live` unchanged.

## Disclaimer

This software is for educational purposes only. Algorithmic trading carries
significant financial risk. Test in a paper environment; nothing here is
financial advice.
