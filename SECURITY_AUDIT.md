# Security audit: imported Vibe-Trading snapshot

Date: 2026-07-23

Audited snapshot: `HKUDS/Vibe-Trading@0aa45a9ff3df58fab1c50f5400d9b112d19cacc6`

## Verdict

No evidence of a malicious implant, credential stealer, cryptominer, obfuscated payload, network bootstrapper, or hidden persistence mechanism was found in the static review performed so far.

This is not the same as saying the project is low-risk. Vibe-Trading intentionally contains powerful capabilities: arbitrary shell execution when explicitly enabled, execution of generated backtest code, broad outbound market/LLM/broker integrations, OAuth and API credential handling, local file tools, messaging adapters, and paper/live order connectors. Those are legitimate product features but create a large attack surface and must remain gated.

## Scope and methods

- Cloned the public GitHub repository without running project code.
- Pinned and reviewed commit `0aa45a9ff3df58fab1c50f5400d9b112d19cacc6`.
- Inventoried all 1,862 tracked files, executable bits, large files, media assets, workflows, scripts, Docker files, manifests, lockfiles, and repository history.
- Parsed 1,244 Python files with `ast.parse`; all parsed successfully.
- Searched tracked content for `eval`/`exec`, shell execution, subprocesses, dynamic imports, base64 decoding, sensitive credential paths, destructive file operations, curl/wget-to-shell patterns, cryptomining indicators, and long opaque payloads.
- Reviewed the intentional shell tool and generated-code runner.
- Ran `npm audit --package-lock-only --json` against the committed frontend lock.
- Ran `pip-audit` against declared Python requirement ranges.
- Ran `git fsck --full --no-dangling`.
- Computed hashes for tracked media assets and confirmed no unexpected native executable inventory was identified by the tracked-file review.

## Findings

### High-risk capability: optional arbitrary shell execution

`agent/src/tools/bash_tool.py:43-53` calls `subprocess.run(command, shell=True, ...)`. This is explicit arbitrary command execution. It is not covert: `agent/mcp_server.py:84-117` keeps shell tools disabled by default and requires `--enable-shell-tools` or `VIBE_TRADING_ENABLE_SHELL_TOOLS` opt-in. Leave this disabled unless operating inside a disposable sandbox.

### High-risk capability: generated Python execution

`agent/src/core/runner.py:459-575` executes generated entry scripts. The runner uses an ephemeral HOME, time/resource limits, and attempts an unprivileged UID drop, but lines 439-457 deliberately fall back to running without that UID drop when unavailable. Static AST defenses reduce risk but are not equivalent to OS isolation. Prefer the hardened container and do not provide generated code with credentials.

### High-risk capability: broker orders and external channels

The repository includes broker connectors, order placement, OAuth/token handling, and many IM/channel adapters. These are expected features, not malicious findings. Keep connectors read-only/paper, require explicit mandates, retain the kill switch, and do not configure channel credentials until needed.

### Medium supply-chain risk: mutable native/dev install paths

- The Docker production path uses digest-pinned base images and `pip install --require-hashes`; frontend production build uses `npm ci --ignore-scripts`.
- `docker-compose.yml:70` uses `npm install` for the optional frontend development profile, which can run package lifecycle scripts and resolve ranges. Prefer `npm ci --ignore-scripts` for initial review/build.
- `pyproject.toml` and `agent/requirements.txt` mostly use version ranges. A direct `pip install -e .` does not provide the same reproducibility as the hash lock.
- The supplied Python lock was generated under Python 3.11. An audit environment running Python 3.12 could not resolve it because of a `caio` version conflict. This is a compatibility/reproducibility issue, not evidence of malware.

### Low provenance caveat: commit signatures not broadly verifiable locally

Recent history contains unsigned commits and merge commits whose signatures could not be validated in the local keyring. Git object integrity passed. Lack of a locally verifiable signature is not itself evidence of malicious code, but the imported SHA should remain pinned and future updates should be re-audited as diffs.

### No dependency advisories found in completed scans

- Frontend: npm reported 0 vulnerabilities across 429 dependencies.
- Python declared ranges: pip-audit reported no known vulnerabilities for the resolved compatible set.

The exact Python hash lock was not successfully audited in the host Python 3.12 environment because it did not resolve there; therefore no exact-lock clean claim is made.

## Safe operating recommendations

1. Use Python 3.11, the hash lock, and the hardened Docker configuration.
2. Keep API and frontend bound to `127.0.0.1`; set an API auth key before any remote access.
3. Keep shell/background tools disabled.
4. Use paper/read-only broker profiles; do not enable live order placement during verification.
5. Run generated strategies only in the hardened container without mounted credentials.
6. Use `npm ci --ignore-scripts` before any frontend build; review any package requiring lifecycle scripts separately.
7. Re-run static and dependency scans for every upstream update; do not track a moving branch blindly.
8. Never reuse a runtime home containing unrelated credentials for this application.

## Limitations

Static review cannot prove the absence of all malicious behavior, especially in third-party packages fetched later, remote services, model-generated code, media parser vulnerabilities, or behavior activated only by credentials. No live broker, LLM, messaging, or external MCP integration was exercised. The two MP4 and image assets were inventoried and hashed but not subjected to full codec-level forensic analysis.

## Addendum: second session, 2026-07-23 (Claude Code)

### Exact hash lock installed and verified under Python 3.11

The original blocker was reproduced and root-caused: the upstream `requirements-lock.txt` is internally inconsistent as published, on any Python version, not just 3.12.

- `caio==0.10.2` conflicts with the lock's own `aiofile==3.11.1`, whose metadata requires `caio~=0.9.0`. This makes a resolver-mediated `pip install --require-hashes -r requirements-lock.txt` fail with `ResolutionImpossible` (the upstream Dockerfile uses exactly that command, so the published Docker path would fail identically with current pip).
- Installing with `--no-deps --require-hashes` instead — exactly upstream's pins, every artifact hash verified against the lock — succeeds under Python 3.11.15. `aiofile` + `caio 0.10.2` import and function together; the `~=0.9.0` metadata is over-strict.
- Two further internal inconsistencies surfaced at runtime: `pydantic-core==2.47.0` is rejected by the lock's own `pydantic==2.13.4` (requires `2.46.4`; hard `SystemError` at import), and `websockets==16.1.1` conflicts with `langgraph-sdk 0.4.2` (`<16`; pip warning only, no observed failure).
- Environment-only remediation: `pydantic-core 2.46.4` was installed into the verification venv. **No upstream file was modified.**

### Provenance note: in-place lock edit found and reverted

A partial reconciliation of the lock (caio downgraded to 0.9.25, setuptools pinned) had been applied **in place** to `requirements-lock.txt` after the parity evidence in this document was recorded, silently invalidating the byte-for-byte claim. The upstream bytes were restored (blob `b64703c4bf40b2e3e40c990f5cce0ba767cf3437` matches the pinned snapshot) and the edited variant preserved as `requirements-lock.reconciled.txt`, a clearly local, unadopted artifact. Note the reconciled variant still contains the broken `pydantic-core` pin, so it is not a working lock either.

### Parity re-verified independently

The pinned upstream snapshot was re-fetched from GitHub and all 1,862 tracked files compared: 0 missing, 0 content mismatches, 0 mode mismatches. Two upstream-tracked files (`assets/Frontend.mp4`, `assets/cli.mp4`) are matched by upstream's own `.gitignore` (`assets/*.mp4`) and were therefore invisible to a plain `git add`; they are now force-staged so the eventual commit cannot silently drop them.

### Dynamic verification results (no credentials, loopback-free)

- Repository safety gates (`tools/ci_grep_gates.sh`): gates a–d pass; gate e's AST check passes when invoked with an explicit interpreter (the script calls unversioned `python`, absent on this host). One pre-existing upstream WARN (non-fatal): `agent/src/providers/llm.py:554`.
- Environment-variable gate (`tools/test_ci_env_var_gate.py`): pass.
- CI syntax checks plus a full-tree sweep: all 1,244 Python files parse under 3.11.
- Frontend: `npm ci --ignore-scripts` (0 vulnerabilities), production build succeeds, vitest 310/310 passed (Node 22.23.1 vs CI's Node 20 — noted deviation).
- Backend: pytest suite run with CI's exact ignore set; results recorded in `BOTo_MIGRATION.md`.

Still not exercised: Docker image build, live API surface comparison, any broker/LLM/channel integration.
