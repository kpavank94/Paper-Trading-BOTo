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

## Android app (`android-app/`, branch `feat/android-capacitor-app`)

Added 2026-08-05. Capacitor wrapper that packages the existing SPA as an
installable Android app, reaching the backend over Tailscale.

- **Upstream parity is intact.** Nothing under `frontend/` and no backend code
  was modified — `git status --porcelain frontend/` is empty. `android-app/build.mjs`
  runs the frontend's own `npm run build` unchanged and copies `dist/` into its
  own web root. The `BASE = ""` problem in `src/lib/api.ts` is solved at runtime
  by `android-app/shim/api-base.js`, which patches `fetch`/`EventSource` before
  the app bundle evaluates, rather than by editing that file.
- **The phone is an untrusted remote client by design.** The backend binds to
  the Tailscale IP, so requests arrive from a `100.x.x.x`
  address, `_is_local_client()` is False, the API key is enforced, and `/live`
  stays blocked by the loopback gate. **Do not switch this to `tailscale serve`**
  — it proxies from `127.0.0.1`, which would make every phone request look
  loopback-local and hand the whole tailnet an auth bypass plus `/live` access.
  Correspondingly, leave `API_ALLOWED_HOSTS` unset.
- Backend needs only env config: `VIBE_TRADING_API_KEY` and a `CORS_ORIGINS`
  that includes `http://localhost` (the Capacitor WebView origin).
- Verified: `npm test` in `android-app/` is 8/8; the frontend build, web-root
  assembly, shim injection, and `cap sync android` all run clean.
- Toolchain installed 2026-08-05: Temurin **JDK 21** at `~/tools/jdk-21.0.12+8`
  and the **Android SDK** at `~/Android/Sdk` (platform 35, build-tools 35.0.0,
  platform-tools). Both work.
- **The APK cannot be compiled on this host, and this is not fixable by
  configuration.** this host is **aarch64**; Google ships `aapt2`, `aapt`,
  `zipalign` and `adb` as **x86-64 binaries only**, with no ARM64 build on
  Google's Maven. `./gradlew assembleDebug` runs **77/77 tasks** and fails at
  exactly one — `:app:processDebugResources` — with
  `aapt2: 1: Syntax error: "(" unexpected` (an x86-64 ELF being run as a shell
  script). The wrapper is sound; only resource compilation is blocked.
  Already ruled out: Ubuntu's arm64 `android-sdk-build-tools` is an empty
  metapackage, its `aapt` is v1 (unusable by AGP 8.x), and Docker — usable
  without sudo — cannot run amd64 images because no qemu binfmt handler is
  registered. Getting an APK needs one of: privileged `tonistiigi/binfmt`
  registration (root-equivalent, system-wide), a GitHub Actions build, or an
  x86-64 machine. See `android-app/README.md`.

## Safety defaults

- Keep shell tools disabled (`VIBE_TRADING_ENABLE_SHELL_TOOLS` unset).
- Keep broker connectors read-only/paper unless the operator explicitly authorizes otherwise.
- Bind services to loopback.
- Prefer the hash-locked dependency path. `requirements-lock.txt` is now reconciled and installs cleanly with `pip install --require-hashes` under **full** dependency resolution — the `--no-deps` workaround is obsolete, and `requirements-lock.reconciled.txt` has been deleted.
- Never commit `.env` files or credentials.
