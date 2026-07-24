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
- [ ] Incorporate the independent reviewer findings and close any blocking findings.

## Like-for-like verification

- [x] Create an isolated Python 3.11 environment from the hash lock without exposing credentials. Done with `pip install --no-deps --require-hashes -r requirements-lock.txt` under Python 3.11.15 — exactly upstream's pins, every hash verified. Environment-only fix afterwards: `pydantic-core==2.46.4` (see Security gate). Test deps (`pytest`, `pytest-cov`, `pytest-socket`) layered on top per `[dev]` extras; upstream file untouched.
- [x] Run repository safety gates and environment-variable gate. `tools/ci_grep_gates.sh` gates a–d pass; gate e passes when its AST helper is invoked with an explicit `python3.11` (script expects unversioned `python` on PATH). `pytest tools/test_ci_env_var_gate.py -q` passes. One pre-existing upstream WARN: `agent/src/providers/llm.py:554`.
- [x] Run Python syntax checks. CI's exact set (compileall `cli`, py_compile of the five entry modules) plus a full-tree sweep: all 1,244 Python files parse under 3.11.
- [x] Run the backend test suite excluding explicitly live/e2e tests, matching upstream CI: `pytest --ignore=agent/tests/e2e_backtest --ignore=agent/tests/test_e2e_harness_v2.py --cov=agent --cov-report=xml --tb=short -q` → **6,145 passed, 13 skipped, 0 failed** in 128s (2026-07-23).
- [x] Install frontend dependencies with lifecycle scripts disabled, then run the TypeScript/Vite build. `npm ci --ignore-scripts` (0 vulnerabilities), `npm run build` succeeds. Host Node 22.23.1 vs CI's Node 20 — noted deviation.
- [x] Run the frontend Vitest suite: **310 passed / 310** across 35 files.
- [ ] Build the hardened Docker image and verify `/live` on loopback only. Note: the upstream Dockerfile's `pip install --require-hashes` (without `--no-deps`) will hit the caio conflict with current pip; expect to need the `--no-deps` form or a reconciled lock.
- [ ] Compare CLI/API/frontend surfaces to the pinned upstream snapshot.
- [ ] Independent final diff/security review.
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

## Legacy baseline caveat

The former BOTo test baseline could not be established in the host environment at import time: `python` was absent, and a clean Python 3.12 install could not satisfy its declared `ib_insync>=0.9.89`. Note (second session): the bar-driven package at the base commit `5fb6bae` was verified separately in the main worktree on 2026-07-23 — 17/17 offline tests pass there using that repo's own `.venv`. No claim is made about the `legacy/` copy running inside *this* worktree's environment.
