# Running Paper Trading BOTo — step by step

This guide covers the bar-driven framework on the `boto-bar-driven` branch: a daily
rebalancer that computes SMA-crossover signals with ATR-scaled position sizing, and runs
the *same code path* for backtesting and live paper trading. Orders are a **dry run by
default** — nothing is ever sent unless you pass `--live`.

Every step below was verified on Linux with Python 3.12 on 2026-07-23.

---

## 1. Prerequisites

- **Python 3.10+** (verified on 3.12) and `git`.
- **A free Alpaca account** — <https://alpaca.markets>. You need *paper* API keys even if
  you only want to backtest, because historical daily bars come from Alpaca's market data
  API (the free IEX feed is enough).
- **Optional — IBKR**: Trader Workstation or IB Gateway if you want orders routed to
  Interactive Brokers instead of Alpaca (see step 8).

## 2. Install

```sh
git clone https://github.com/kpavank94/Paper-Trading-BOTo.git
cd Paper-Trading-BOTo
git checkout boto-bar-driven

python3 -m venv .venv
.venv/bin/pip install -r paper_trading_boto/requirements.txt
```

## 3. Configure

Copy the example config to the repo root and fill in your keys:

```sh
cp paper_trading_boto/.env.example .env
```

Edit `.env` — the minimum for Alpaca paper trading:

| Variable | Value | Why |
|---|---|---|
| `BROKER` | `alpaca` | which venue receives orders |
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | your **paper** keys | data + trading auth |
| `ALPACA_PAPER` | `true` | routes orders to the paper account |
| `ALPACA_FEED` | `iex` | free data feed (`sip` needs a paid subscription) |
| `SYMBOLS` | e.g. `SPY,QQQ,IWM` | the universe to trade |

Worth reviewing before going further: `RISK_PER_TRADE` (default 0.01 — 1% of equity at
risk per position), `MAX_WEIGHT`, `MAX_PORTFOLIO_EXPOSURE`, and `MAX_DRAWDOWN_STOP`
(default 0.20 — a 20% drawdown flattens the book and halts new entries).

**Never commit `.env`** — it is gitignored; keep it that way.

## 4. Sanity check (no keys needed)

```sh
.venv/bin/python -m pytest paper_trading_boto/tests -q
```

Expected: `17 passed`. This runs entirely offline against synthetic bars.

## 5. Backtest before anything else

```sh
.venv/bin/python -m paper_trading_boto.bot backtest --out equity.csv
```

Prints a JSON block of metrics — CAGR, Sharpe, max drawdown, Calmar, turnover, hit rate —
and writes the equity curve to `equity.csv`. Try parameter variants without touching
config:

```sh
.venv/bin/python -m paper_trading_boto.bot backtest --symbols SPY,QQQ --fast 10 --slow 50
```

If the numbers don't justify trading, stop here and iterate — that's the point of this step.

## 6. Dry-run a rebalance

```sh
.venv/bin/python -m paper_trading_boto.bot once
```

- Outside market hours it logs `market is closed, no action taken` and exits — expected.
- During market hours it logs equity, target weights, and each intended order prefixed
  `DRY`. **Nothing is sent.** Read these lines and check they make sense (sane share
  counts, sane notional).

## 7. Trade on the paper account

Single rebalance with real paper orders:

```sh
.venv/bin/python -m paper_trading_boto.bot once --live
```

Continuous operation — wakes ~15 minutes before each market close, rebalances against the
nearly-complete daily bar, then sleeps until the next session:

```sh
.venv/bin/python -m paper_trading_boto.bot loop --live
```

(`--minutes-before-close N` adjusts the trigger; `Ctrl-C` exits cleanly and writes reports.)

To close every open position at any time:

```sh
.venv/bin/python -m paper_trading_boto.bot flatten
```

Verify fills in the Alpaca dashboard (paper account) after the first `--live` run.

## 8. Optional: route orders through IBKR instead

1. In TWS/IB Gateway: enable *ActiveX and Socket Clients*, disable *Read-Only API*, and
   use the **paper** port `7497` (live is `7496` — don't).
2. In `.env`: set `BROKER=ibkr`, `TWS_HOST=127.0.0.1`, `TWS_PORT=7497`, `CLIENT_ID=1`.
3. Keep your Alpaca keys set — historical bars still come from Alpaca's data API; only
   order routing changes.

## 9. Where output goes

- `reports/` — CSV + HTML session reports (generated when a session recorded trades).
- `trades.db` — SQLite trade/order log on the IBKR path (set `DB_PATH=` empty to disable).
- Add `--verbose` to any command for debug logging.

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `RuntimeError: APCA_API_KEY_ID and APCA_API_SECRET_KEY must be set` | `.env` missing at the directory you run from, or keys empty. |
| `subscription does not permit querying recent SIP data` | Set `ALPACA_FEED=iex`. |
| `market is closed, no action taken` | Expected outside regular trading hours. |
| `no targets produced, check symbols and warmup length` | The strategy needs ~101 daily bars of history per symbol (slow SMA + 1); check `SYMBOLS` spelling and `HISTORY_DAYS`. |
| `pip` can't find `ib_insync>=0.9.89` | Fixed on this branch (pin is now `>=0.9.86`, the last release PyPI has). |
| IBKR connect fails | TWS/Gateway not running, API not enabled, or wrong port. |

---

## Note on the other branches

- **`main`** holds a separate, event-driven rewrite (engine/portfolio/sim-broker design)
  with its own CLI — the two designs share a root but are alternatives, not versions of
  each other.
- **`feat/vibe-trading-parity`** is a byte-for-byte import of the upstream
  [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) platform (this package
  preserved under `legacy/`). It is a different product with its own README and run
  procedure, and its deployment gates (hardened Docker build, final review) are still
  open — see `BOTo_MIGRATION.md` on that branch before running it. Its safety defaults
  (shell tools off, paper/read-only brokers, loopback binds) are documented in its
  `AGENT-BRIEF.md`.
