# Paper-Trading BOTo agent brief

Last updated: 2026-07-23 by Claude Code (second session; import and static review by Hermes)

## Active migration

- Branch: `feat/vibe-trading-parity`
- Worktree: `/home/zandu/projects/.worktrees/paper-trading-boto-vibe-parity`
- Base: `boto-bar-driven` at `5fb6bae0ab0fd673ae10b85b541f49739de18b2c`
- Imported upstream: HKUDS/Vibe-Trading at `0aa45a9ff3df58fab1c50f5400d9b112d19cacc6`
- Goal: make this repository functionally like-for-like with that pinned Vibe-Trading snapshot while retaining the former BOTo implementation under `legacy/`.

## Current verified state

- All 1,862 upstream tracked files are byte-for-byte and mode-identical to the pinned snapshot — re-verified independently on 2026-07-23 against a fresh fetch of the pinned SHA (0 missing, 0 mismatch, 0 mode).
- The intended commit is fully **staged**: 1,862 upstream files + 33 `legacy/` renames (all R100) + 4 local additions (`AGENT-BRIEF.md`, `BOTo_MIGRATION.md`, `SECURITY_AUDIT.md`, `requirements-lock.reconciled.txt`). `assets/Frontend.mp4` and `assets/cli.mp4` are upstream-tracked but matched by upstream's own `.gitignore`; they are force-staged — never rebuild the index with a plain `git add .` without re-adding them with `-f`.
- An in-place edit to `requirements-lock.txt` (partial caio/setuptools reconciliation) was found and reverted to upstream bytes; the edit is preserved as `requirements-lock.reconciled.txt` (local artifact, not adopted, itself still broken — see below).
- The upstream lock is internally inconsistent as published: `caio==0.10.2` vs `aiofile`'s `caio~=0.9.0` metadata (resolver-fatal), `pydantic-core==2.47.0` vs `pydantic==2.13.4` requiring `2.46.4` (import-fatal), `websockets==16.1.1` vs `langgraph-sdk<16` (warning only). Workaround that preserves upstream pins: install with `--no-deps --require-hashes` under Python 3.11, then fix `pydantic-core==2.46.4` in the environment only.
- Dynamic gates passed on 2026-07-23 (details and exact commands in `BOTo_MIGRATION.md`): repo safety gates, env-var gate, CI syntax checks, full 1,244-file AST sweep, hash-verified 3.11 install, frontend `npm ci --ignore-scripts` + build + vitest 310/310, backend pytest suite with CI's ignore set.
- Static malicious-code and dependency review is recorded in `SECURITY_AUDIT.md` (including the 2026-07-23 addendum). No upstream code was executed before static review.

## Remaining verification

See `BOTo_MIGRATION.md`. Do not mark build/test items complete without fresh command output. Do not enable shell tools, live broker order placement, external messaging channels, or network exposure merely to run tests.

**All gates closed 2026-07-24.** The platform was adopted onto `main` at the operator's explicit request: `main`'s tree is now byte-identical to the parity branch (merge with both parents, no force-push), `legacy/` was removed, and the dependency lock was reconciled and adopted. Hardened Docker build succeeds and `/live` is loopback-only; 1,861 of 1,862 upstream files remain byte-identical (sole deviation: `requirements-lock.txt`); security review recorded one accepted advisory (`setuptools==82.0.1`, sdist/macOS-only, pinned exactly by `ccxt`). Details and evidence in `BOTo_MIGRATION.md` under "Adoption".

## Safety defaults

- Keep shell tools disabled (`VIBE_TRADING_ENABLE_SHELL_TOOLS` unset).
- Keep broker connectors read-only/paper unless the operator explicitly authorizes otherwise.
- Bind services to loopback.
- Prefer the hash-locked dependency path. `requirements-lock.txt` is now reconciled and installs cleanly with `pip install --require-hashes` under **full** dependency resolution — the `--no-deps` workaround is obsolete, and `requirements-lock.reconciled.txt` has been deleted.
- Never commit `.env` files or credentials.
