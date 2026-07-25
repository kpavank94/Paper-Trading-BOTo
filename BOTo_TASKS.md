# BOTo × Vibe-Trading — task list

Working plan for adapting the Vibe-Trading platform to the operator's setup:
local vLLM (Qwen) for reasoning, IBKR/Alpaca paper trading, SearXNG search,
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
- [x] **Phase 2 — Alpaca news + sentiment tool** — `get_alpaca_news` (auto-
  discovered BaseTool), real-time US news + coarse lexicon sentiment tag.
  Self-disables without a key. Mock-tested. Files:
  `agent/src/tools/alpaca_news_tool.py`, `agent/tests/test_alpaca_integrations.py`.
  **Activates once you set** `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`.
- [x] **Phase 3 — Alpaca market-data loader** — registered source `alpaca` for
  `us_equity` (daily bars, IEX feed, paginated), in the fallback chain after the
  other key-gated REST sources. Mock-tested. Files:
  `agent/backtest/loaders/alpaca_loader.py`, `agent/backtest/loaders/registry.py`,
  `agent/SKILL.md` (source count 23→24), test_registry / manifest updated.
  **Activates once you set** the Alpaca key.

---

## ⛔ Still blocked on an input from you

- [ ] **Phase 5 — Verify paper connectors end-to-end.** (Code is ready; these are
  live-verification steps.)
  - Alpaca (`alpaca-paper` connector + the new news tool + data loader) —
    **needs** a free key: `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` in
    `agent/.env`. → <https://alpaca.markets> (paper keys suffice).
  - IBKR (`ibkr-paper-local`, already the default connector) — **needs** TWS /
    IB Gateway running on paper port `7497` with the API enabled.

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
- **Free APIs selected:** Alpaca (trading + data + news). GDELT / Finnhub /
  Alpha Vantage were considered but not selected — GDELT (no key) remains a
  zero-cost add later if broader news breadth is wanted.
- **Search:** SearXNG is primary; ddgs remains the automatic fallback.
- **Everything stays local** with the vLLM setup — prompts, generated code, and
  results never leave the box; only public market-data/news fetches go out.
- **Upstream parity:** changes are kept minimal and documented; the tree was
  byte-identical to `0aa45a9` except the reconciled lock before this feature work.
