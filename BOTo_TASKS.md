# BOTo × Vibe-Trading — task list

Working plan for adapting the Vibe-Trading platform to the operator's setup:
local vLLM (Qwen) for reasoning, IBKR paper trading, SearXNG search,
free news/sentiment feeds, and TradingView webhook signals. The built-in
backtest engine is kept (TradingView has no backtesting API — see Notes).

Last updated: 2026-07-25. Legend: ✅ done · 🔜 ready to build · ⛔ blocked on an
input · ⬜ planned.

---

## ✅ Done and verified

- [x] **Adopt Vibe-Trading onto `main`** — tree byte-identical to the pinned
  upstream snapshot (`0aa45a9`), both parents preserved, `legacy/` removed.
- [x] **Dependency lock reconciled** — 6 constraint violations + 7 missing pins
  fixed; 193 pkgs install hash-verified with full resolution.
- [x] **Gates closed** — backend 6145 passed; frontend build + vitest 310/310;
  hardened Docker build; `/live` loopback-only, non-root; security review.
- [x] **Local LLM wired** — vLLM `nvidia/Qwen3.6-35B-A3B-NVFP4` via the `ollama`
  provider (no key). Preflight OK; tool-calling verified end-to-end.
- [x] **Backtest timeout fixed** — root cause was the 90s browser SSE limit, not
  the engine (the run produced complete, validated results). Raised
  `VIBE_TRADING_SSE_TIMEOUT`, `TIMEOUT_SECONDS`, `TOOL_TIMEOUT_SECONDS`.
- [x] **Phase 1 — SearXNG search** — added as the top-priority backend in the
  agent's `web_search` tool (falls back to ddgs), pointed at `localhost:8080`.
  Verified live (`backend: searxng`); CI env-gate green. Files:
  `agent/src/tools/web_search_tool.py`, `agent/src/config/env_schema.py`.
- [x] **Phase 4 — TradingView webhook receiver** — `POST /webhook/tradingview`,
  secret-guarded (fail-closed), **advisory-only** (records signals; never places
  orders — execution stays behind the order guard by design). Readback at
  `GET /webhook/tradingview/signals`. 6/6 tests; all paths verified live with
  `curl`. Files: `agent/src/api/webhook_routes.py`, `agent/api_server.py`,
  `agent/src/config/env_schema.py`, `agent/tests/test_webhook_tradingview.py`.
- [x] **Phase 2 — GDELT news + sentiment tool** *(replaced Alpaca — see Canada
  note)*. `get_gdelt_news` (auto-discovered BaseTool): global news + GDELT's own
  aggregate "tone" sentiment, **no API key, no signup, works from Canada**.
  Rate-limit tolerant (429 → returns articles, degrades tone gracefully).
  Mock-tested + verified live. File: `agent/src/tools/gdelt_news_tool.py`,
  `agent/tests/test_gdelt_news_tool.py`.
- [x] **Phase 3 — Market data: already covered, no US signup needed.** The
  platform ships Canada-accessible loaders that need no key —
  `yfinance` / `yahoo` / `stooq` (US + intl equities) — plus optional free
  *international*-signup keys (`finnhub`, `alphavantage`, `tiingo`, `fmp`). The
  Alpaca data loader was removed (US-only account). No build needed.

---

## 🇨🇦 Canada note (2026-07-25)

Alpaca brokerage — and its data/news API, which needs the same account — is
**US-only**, so it was removed. The stack now uses only Canada-accessible pieces:

| Need | Canada-friendly choice | Signup? |
|---|---|---|
| Paper trading | **IBKR** (`ibkr-paper-local`, already default) | IBKR works in Canada |
| Market data | `yfinance` / `yahoo` / `stooq` (built in) | none |
| News + sentiment | **GDELT** (`get_gdelt_news`) | none |
| Web search | **SearXNG** (your instance) | none |
| Signals | **TradingView webhooks** | none |
| Optional extra data | Finnhub / AlphaVantage / Tiingo / FMP | free, *international* |

---

## ⛔ Still blocked on an input from you

- [ ] **Phase 5 — Verify IBKR paper trading end-to-end.** (Code is ready; this is
  a live-verification step.) IBKR (`ibkr-paper-local`, already the default
  connector, works in Canada) — **needs** TWS / IB Gateway running on paper port
  `7497` with the API enabled. Everything else (search, news/sentiment, data,
  webhooks) needs no further input and is live now.

---

## ✅ Housekeeping — done this pass

- [x] **Documented deviations from upstream parity** in `BOTo_MIGRATION.md`.
- [x] **Committed the feature work** (see the "Feature work" commit).
- [x] **Pushed `main` to origin.**
- [x] **Cleaned up scratch worktrees.**

---

## Testing note (important)

The backend suite is **hermetic only without a populated `agent/.env`** — that
file is autoloaded by `python-dotenv`, and `SEARXNG_URL` in it makes the
web-search tests take the SearXNG path instead of their mocked ddgs path (5
spurious failures in `test_web_search_tool` / `test_security_scanner` /
`test_ocr_engine`). Upstream CI has no `agent/.env`, so it never sees this. To
run the full suite locally, move `agent/.env` aside first:

```sh
mv agent/.env agent/.env.bak && (cd agent && PYTHONPATH=. ../.venv/bin/python -m pytest \
  --ignore=tests/e2e_backtest --ignore=tests/test_e2e_harness_v2.py -q) ; mv agent/.env.bak agent/.env
```

Verified this pass: **6158 passed, 13 skipped, 0 failed** (hermetic).

---

## Notes / decisions on record

- **TradingView has no backtesting API.** Its Strategy Tester runs only in the
  browser; scraping violates ToS. Decision: keep Vibe-Trading's own (working)
  backtest engine, and use TradingView **webhook alerts** for live signals
  (Phase 4). This was chosen over the ToS-gray `tradingview-ta` ratings scrape.
- **Free APIs:** Alpaca was the first pick but is US-only; replaced by **GDELT**
  (news/sentiment, no signup) after the Canada constraint surfaced. Finnhub /
  AlphaVantage / Tiingo / FMP remain available as optional free international-
  signup data keys the platform already supports.
- **Search:** SearXNG is primary; ddgs remains the automatic fallback.
- **Everything stays local** with the vLLM setup — prompts, generated code, and
  results never leave the box; only public market-data/news fetches go out.
- **Upstream parity:** changes are kept minimal and documented; the tree was
  byte-identical to `0aa45a9` except the reconciled lock before this feature work.
