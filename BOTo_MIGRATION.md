# Vibe-Trading parity migration

Upstream snapshot: `HKUDS/Vibe-Trading@0aa45a9ff3df58fab1c50f5400d9b112d19cacc6`

## Import

- [x] Create isolated `feat/vibe-trading-parity` worktree from `boto-bar-driven`.
- [x] Preserve the former BOTo implementation under `legacy/`.
- [x] Import every upstream tracked file.
- [x] Verify all 1,862 imported files byte-for-byte and verify executable-mode parity.
- [x] Re-verify independently (2026-07-23, second session): fresh fetch of the pinned SHA, all 1,862 files compared — 0 missing, 0 content mismatch, 0 mode mismatch.
- [x] Preserve upstream MIT license, NOTICE, attribution, documentation, frontend, backend, tests, deployment files, and lockfiles.
- [x] Stage the full intended commit: 1,862 upstream files + 33 `legacy/` renames (R100) + 4 local docs. `assets/Frontend.mp4` and `assets/cli.mp4` are upstream-tracked but matched by upstream's own `.gitignore` (`assets/*.mp4`); they are force-staged (`git add -f`) so the commit cannot silently drop them.

## Security gate

- [x] Inspect source, scripts, workflows, Docker files, manifests, and tracked binary inventory without executing upstream code.
- [x] Scan Python files for parse errors and suspicious execution, obfuscation, credential-path, destructive-operation, and cryptomining patterns.
- [x] Run npm advisory audit against `frontend/package-lock.json`.
- [x] Run Python advisory audit against declared runtime requirements.
- [x] Root-cause the lock resolution failure. The upstream lock is internally inconsistent **as published, on any Python version**: `caio==0.10.2` conflicts with its own `aiofile==3.11.1` (`caio~=0.9.0` metadata) so resolver-mediated `--require-hashes` install fails; `pydantic-core==2.47.0` is rejected at import by its own `pydantic==2.13.4` (requires `2.46.4`); `websockets==16.1.1` conflicts with `langgraph-sdk<16` (warning only). A previous in-place partial fix to `requirements-lock.txt` was reverted to restore upstream bytes (blob `b64703c` verified) and preserved as `requirements-lock.reconciled.txt` — note it still carries the broken pydantic-core pin, so it is not a working lock either.
- [x] Incorporate the independent reviewer findings and close any blocking findings. Closed 2026-07-24 — see "Adoption" below. The lock has been reconciled and adopted; a full metadata scan found **six** violations, three more than were recorded above (`ccxt` additionally pins `cffi==2.0.0`, `charset-normalizer==3.4.7`, `yarl==1.24.2` against lock pins `2.1.0` / `3.4.9` / `1.24.5`), plus **seven** transitive dependencies missing from the lock entirely.

## Like-for-like verification

- [x] Create an isolated Python 3.11 environment from the hash lock without exposing credentials. Done with `pip install --no-deps --require-hashes -r requirements-lock.txt` under Python 3.11.15 — exactly upstream's pins, every hash verified. Environment-only fix afterwards: `pydantic-core==2.46.4` (see Security gate). Test deps (`pytest`, `pytest-cov`, `pytest-socket`) layered on top per `[dev]` extras; upstream file untouched.
- [x] Run repository safety gates and environment-variable gate. `tools/ci_grep_gates.sh` gates a–d pass; gate e passes when its AST helper is invoked with an explicit `python3.11` (script expects unversioned `python` on PATH). `pytest tools/test_ci_env_var_gate.py -q` passes. One pre-existing upstream WARN: `agent/src/providers/llm.py:554`.
- [x] Run Python syntax checks. CI's exact set (compileall `cli`, py_compile of the five entry modules) plus a full-tree sweep: all 1,244 Python files parse under 3.11.
- [x] Run the backend test suite excluding explicitly live/e2e tests, matching upstream CI: `pytest --ignore=agent/tests/e2e_backtest --ignore=agent/tests/test_e2e_harness_v2.py --cov=agent --cov-report=xml --tb=short -q` → **6,145 passed, 13 skipped, 0 failed** in 128s (2026-07-23).
- [x] Install frontend dependencies with lifecycle scripts disabled, then run the TypeScript/Vite build. `npm ci --ignore-scripts` (0 vulnerabilities), `npm run build` succeeds. Host Node 22.23.1 vs CI's Node 20 — noted deviation.
- [x] Run the frontend Vitest suite: **310 passed / 310** across 35 files.
- [x] Build the hardened Docker image and verify `/live` on loopback only. Done 2026-07-24. The predicted failure was real: `Dockerfile:37` runs `pip install --require-hashes -r requirements-lock.txt` without `--no-deps`, which cannot resolve the published lock. With the reconciled lock adopted as `requirements-lock.txt`, `docker build` succeeds unmodified. Container verified: `/live` → `{"status":"healthy"}`, listener bound `127.0.0.1:8899` only, connection from the host LAN address (`192.168.2.152:8899`) **refused**, process runs as non-root `uid=1000(vibe)`, Docker healthcheck reports `healthy`.
- [x] Compare CLI/API/frontend surfaces to the pinned upstream snapshot. Done 2026-07-24 by blob-level comparison against a fresh fetch of `0aa45a9`: of 1,862 upstream files, **1,861 are byte-identical**, 0 missing, 0 mode changes. The single content deviation is `requirements-lock.txt` (reconciliation, below). Because every executable file — Python, TypeScript, config — is byte-identical, the CLI, API and frontend surfaces are identical by construction. Recorded for reference: 53 API routes (`/openapi.json`), 16 CLI subcommands, 9 frontend routes.
- [x] Independent final diff/security review. Done 2026-07-24 — see "Adoption" below.
- [x] Commit the migration locally and push. Done 2026-07-23 on explicit operator request, with the three items above still open — they now gate *adoption/deployment*, not the branch history.

## Evidence

- Source parity (re-verified 2026-07-23 against a fresh fetch of the pinned SHA): `upstream_files=1862`, `missing_count=0`, `mismatch_count=0`, `mode_mismatch_count=0`. Staged index verified identically (plus 33 `legacy/` R100 renames and 4 local docs; no other extras).
- Python AST parse: 1,244 files parsed under 3.11.15, 0 failures.
- Hash-locked install: all lock artifacts downloaded and hash-verified under `--no-deps --require-hashes`, Python 3.11.15.
- Backend tests: 6,145 passed, 13 skipped, 0 failed (CI ignore set, with coverage).
- Frontend: npm audit 0 vulnerabilities across 429 dependencies; build clean; vitest 310/310.
- pip-audit of declared requirement ranges: no known vulnerabilities found. This resolves current compatible packages, not necessarily every exact package in `requirements-lock.txt`.
- Opaque payload scan: 0 long base64/hex payload findings.
- Git object integrity: `git fsck --full --no-dangling` passed.

## Adoption (2026-07-24)

The operator elected to adopt Vibe-Trading as the project rather than continue the
bar-driven framework. Three things changed on `main`:

1. **`main` replaced.** A merge records both parents so main's prior event-driven history
   stays reachable, but the resulting tree is byte-identical to `feat/vibe-trading-parity`.
   No force-push; `git revert -m 1` undoes it.
2. **`legacy/` removed** (33 files). The former BOTo implementation lives on
   `boto-bar-driven` (and `origin/boto-bar-driven`), which remains the maintained
   bar-driven framework with its own `RUNNING.md`. Nothing in the Vibe-Trading tree
   referenced `legacy/`.
3. **The lock reconciled and adopted.** `requirements-lock.txt` is now the working lock;
   `requirements-lock.reconciled.txt` (an unadopted partial draft that still carried the
   fatal `pydantic-core` pin) is deleted.

### The lock deviation — the only content change from upstream

Upstream's lock cannot be installed by any resolver on any Python version. A full metadata
scan of all 186 pins found six violated constraints; a resolution pass found seven
transitive dependencies absent from the lock entirely.

| Package | Upstream | Adopted | Why |
|---|---|---|---|
| `caio` | 0.10.2 | 0.9.25 | `aiofile==3.11.1` requires `caio~=0.9.0` |
| `cffi` | 2.1.0 | 2.0.0 | `ccxt==4.5.67` requires `cffi==2.0.0` |
| `charset-normalizer` | 3.4.9 | 3.4.7 | `ccxt==4.5.67` requires `==3.4.7` |
| `yarl` | 1.24.5 | 1.24.2 | `ccxt==4.5.67` requires `==1.24.2` |
| `websockets` | 16.1.1 | 15.0.1 | `langgraph-sdk==0.4.2` requires `<16,>=14` |
| `pydantic-core` | 2.47.0 | 2.46.4 | `pydantic==2.13.4` requires `==2.46.4` |
| *added* | — | `setuptools==82.0.1` | required by `ccxt`, absent from lock |
| *added* | — | `aiohttp-fast-zlib`, `zlib-ng` | required by `ccxt`, absent from lock |
| *added* | — | `jaraco.classes`, `jaraco.context`, `jaraco.functools`, `backports.tarfile` | required by `keyring`, absent from lock |

Every violated pin moved to the version its dependent declares — never the reverse — and
**version drift against upstream's remaining pins is zero**: all other upstream versions
are preserved exactly. A re-scan of the adopted lock reports zero violations.

Verified: `pip install --require-hashes` with **full dependency resolution** succeeds for
all 193 packages under Python 3.11.15. The `--no-deps` workaround is no longer required.

### Security review

- **Frontend:** `npm audit` — 0 vulnerabilities.
- **Python:** `pip-audit` against the adopted lock — one advisory, **accepted**:
  `setuptools==82.0.1`, CVE-2026-59890 / GHSA-h35f-9h28-mq5c, fixed in 83.0.0.
  Not upgradable: `ccxt==4.5.67` pins `setuptools==82.0.1` exactly, so clearing it means
  deviating from upstream's `ccxt` pin. Impact is nil for this project: the flaw is a
  `MANIFEST.in` exclusion bypass when **building an sdist** on **macOS APFS/HFS+**
  (`CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:L/A:N`). Nothing in this project's runtime,
  Docker build, or test path builds an sdist, and both the dev environment and the runtime
  image are Linux. Revisit when `ccxt` relaxes the pin.
- **Secrets:** no `.env`, key, or credential file is tracked; `.env` and `agent/.env` are
  both gitignored.
- **Safety defaults confirmed in code:** `VIBE_TRADING_ENABLE_SHELL_TOOLS` defaults to
  `False` (`agent/src/config/env_schema.py:248`); `docker-compose.yml` publishes both ports
  on `127.0.0.1` only; the container runs non-root.
- **Live-order path reviewed** (`agent/src/live/order_guard.py`, `enforcement.py`): every
  check is fail-closed — invalid/expired mandate, kill switch, unparseable intent, and
  missing quotes all DENY before any broker call; the daily counter increments only on a
  confirmed non-error fill; `repeatable = False` prevents silent re-issue. No finding.

**Still requires the operator, by design:** the agent will not start without an LLM
provider credential, and live trading additionally requires an explicit mandate. Neither
was configured during this verification.

## Feature deviations from upstream (2026-07-25)

Beyond the reconciled lock, the following intentional changes extend the platform
for the operator's setup. Kept minimal and mirroring existing patterns; each is
covered by tests. These are the only edits to upstream files.

| Capability | Files touched | Nature |
|---|---|---|
| **SearXNG search** | `src/tools/web_search_tool.py`, `src/config/env_schema.py` | New top-priority backend in the existing `web_search` tool (falls back to ddgs); `SEARXNG_URL` / `SEARXNG_TIMEOUT_S` config. Mirrors the existing Aliyun-IQS fast-path. |
| **TradingView webhook** | `src/api/webhook_routes.py` (new), `api_server.py`, `src/config/env_schema.py` | Secret-guarded, fail-closed, **advisory-only** signal receiver (`POST /webhook/tradingview`, `GET /webhook/tradingview/signals`). Never places orders — execution stays behind the mandate/order-guard by design. |
| **GDELT news + sentiment tool** | `src/tools/gdelt_news_tool.py` (new) | Auto-discovered `get_gdelt_news` BaseTool: global news + GDELT aggregate "tone" sentiment. **No key, no signup, Canada-accessible.** Rate-limit tolerant. |
| **Config** | `src/config/env_schema.py` | Added the SearXNG and TradingView fields above (Pydantic schema, so the CI env-gate stays green). |

**Canada pivot (2026-07-25):** the operator is in Canada and cannot sign up for
Alpaca (US-only brokerage; its data/news API needs the same account). The Alpaca
news tool and `us_equity` data loader added earlier were therefore **removed**
and replaced with GDELT (news/sentiment, no signup). Market data uses the
platform's existing no-key loaders (`yfinance` / `yahoo` / `stooq`); paper trading
uses IBKR (`ibkr-paper-local`, already the default connector, works in Canada).
The upstream Alpaca *connector* is left untouched (it is upstream code and inert
without a key). Source count returned to 23.

New tests: `test_webhook_tradingview.py` (6), `test_gdelt_news_tool.py` (6). Full
hermetic suite: **6157 passed, 0 failed**. See the testing note in `BOTo_TASKS.md`
— the suite must run without a populated `agent/.env`.

The immediate motivation was a reported backtest "execution timeout" that was
**not** an engine failure: the run produced complete, validated artifacts, but
the 90s browser SSE limit expired first on the slow local model. Fixed by raising
`VIBE_TRADING_SSE_TIMEOUT` / `TIMEOUT_SECONDS` / `TOOL_TIMEOUT_SECONDS` in
`agent/.env` (gitignored).

**Not built (by decision):** TradingView backtesting has no official API (Strategy
Tester is browser-only; scraping violates ToS), so the built-in backtest engine
is kept and TradingView is integrated via inbound webhooks only.

## Legacy baseline caveat

The former BOTo test baseline could not be established in the host environment at import time: `python` was absent, and a clean Python 3.12 install could not satisfy its declared `ib_insync>=0.9.89`. Note (second session): the bar-driven package at the base commit `5fb6bae` was verified separately in the main worktree on 2026-07-23 — 17/17 offline tests pass there using that repo's own `.venv`. No claim is made about the `legacy/` copy running inside *this* worktree's environment. As of the 2026-07-24 adoption, `legacy/` no longer exists on `main`; use the `boto-bar-driven` branch for that code.
