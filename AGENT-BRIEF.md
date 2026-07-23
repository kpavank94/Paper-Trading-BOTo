# AGENT-BRIEF — Paper-Trading-BOTo

Personal passion project. Clone of https://github.com/kpavank94/Paper-Trading-BOTo,
redesigned 2026-07-23 from an AI-generated scaffold into an event-driven bot
(branch `redesign-event-driven`).

## Workspace rules
- Commit locally; **never push unless explicitly asked**.
- Paper trading only. Port 7497. Never point at a live account (7496).

## Invariants — do not regress
- Positions update **only from confirmed fills** (`Portfolio.apply_fill`);
  never optimistically on order submission.
- A missing/NaN price is *no information*: it must never trigger an exit
  (`RiskManager.should_exit`) or pass into indicators (`_clean_price` in
  `broker/ibkr.py`). Regression tests exist in `tests/test_risk.py`.
- Stops are attached broker-side on entry (`OrderRequest.stop_loss_price`);
  the engine check is only a backstop.
- Webhook auth is fail-closed: no `TRADINGVIEW_SECRET` → no service.
- Strategies stay pure (bars in, signals out) so backtest == live.

## Gotchas
- Dependency is **ib_async** (maintained fork), not ib_insync — the archived
  original's requirements pin (`>=0.9.89`) never existed on PyPI.
- `SimulatedBroker` fills at *next* bar open by design (no lookahead). Tests
  encode this; "fix"ing it to same-bar close breaks backtest honesty.
- This host is ARM64; IB Gateway is x86 and runs elsewhere on the network
  (set TWS_HOST accordingly).
- Tests are network-free; the yfinance path is only exercised via
  `boto backtest` manually.

## Verify
`.venv/bin/pytest -q` then a smoke backtest:
`boto backtest --symbol AAPL --start 2024-01-01 --end 2025-01-01`
