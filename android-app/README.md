# BOTo Trading — Android app

Packages the existing Vibe-Trading SPA as an installable Android app using
[Capacitor](https://capacitorjs.com/). The phone reaches the backend over
Tailscale; the backend is never exposed to the local wifi or the public internet.

## Design: why this lives outside `frontend/`

`AGENT-BRIEF.md` records that 1,861 of 1,862 files are byte-identical to the
pinned upstream `HKUDS/Vibe-Trading` snapshot. This wrapper is built to keep that
property exactly as it is:

- **Nothing under `frontend/` is modified** — not `src/lib/api.ts`, not
  `vite.config.ts`, not `package.json`. `build.mjs` runs that project's own
  `npm run build` unchanged and copies the output here.
- **No backend code is modified.** Everything the phone needs is reachable
  through existing environment variables.

The upstream SPA hardcodes `BASE = ""` in `src/lib/api.ts` and issues every
request as a root-relative path, which only works when the API shares an origin
with the page. Instead of patching that file, `shim/api-base.js` patches `fetch`
and `EventSource` at runtime, before the app bundle evaluates. See the comments
in that file for the mechanism.

## Security model

**The phone is an untrusted remote client, by design.**

The backend binds to this machine's Tailscale IP, so requests from the phone
arrive from a `100.x.x.x` tailnet address. `_is_local_client()` in
`agent/src/api/security.py` returns `False` for those, which means:

- **The API key is enforced.** The loopback auth bypass does not apply.
- **`/live` stays blocked.** `agent/src/api/system_routes.py:337` rejects any
  client that is not `127.0.0.1`/`::1`. Live-trading routes are unreachable from
  the phone. This is intentional — treat the app as read/paper only.

### Do not use `tailscale serve` for this

It looks like the obvious choice and it is a trap. `tailscale serve` proxies from
the tailnet to `127.0.0.1`, so the backend would see **every** phone request as
originating from loopback — silently enabling the auth bypass and unblocking
`/live` for anything on your tailnet.

In practice the `_reject_untrusted_loopback_host` DNS-rebinding middleware would
first reject those requests with `403 Untrusted local API host`, and the tempting
fix — adding the tailnet name to `API_ALLOWED_HOSTS` — is precisely what grants
loopback-level trust to the whole tailnet. Bind to the tailnet IP instead, as
below, and leave `API_ALLOWED_HOSTS` unset.

### Other hardening applied

- `android:allowBackup="false"` in the manifest. The API key lives in WebView
  `localStorage`; with backup enabled it could be pulled off the device via
  `adb backup`.
- Cleartext traffic is denied by default and re-permitted only for `localhost`
  and your tailnet domain — see `android/app/src/main/res/xml/network_security_config.xml`.

## Prerequisites

The toolchain is installed and working:

| Requirement | Status here | Notes |
|---|---|---|
| **JDK 21** | ✓ `~/tools/jdk-21.0.12+8` | Temurin, aarch64. AGP 8.7.2 needs 17+ |
| **Android SDK** | ✓ `~/Android/Sdk` | platform 35, build-tools 35.0.0, platform-tools |
| Node 18+ | ✓ v22.23.1 | |
| Tailscale | ✓ running | `tailscale status` gives this host's tailnet name |

```bash
export JAVA_HOME="$HOME/tools/jdk-21.0.12+8"
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
```

The scaffold targets `compileSdk`/`targetSdk` **35**, `minSdk` 23 (see
`android/variables.gradle`) — Android 6.0 and up.

## ⚠️ This machine cannot compile the APK (aarch64)

This host is **aarch64** (Cortex-X925). Google ships the Android build tools as
**x86-64 binaries only** — there is no Linux ARM64 distribution:

```
$ file $ANDROID_HOME/build-tools/35.0.0/aapt2
ELF 64-bit LSB pie executable, x86-64
$ ./aapt2 version
bash: ./aapt2: cannot execute binary file: Exec format error
```

`aapt2`, `aapt`, `zipalign` and `adb` are all x86-64. (`d8` and `apksigner` are
shell scripts over JARs and run fine.) Google's Maven has no ARM64 classifier
for aapt2 — `aapt2-8.7.2-…-linux-arm64.jar` and every aarch64 spelling 404.

`./gradlew assembleDebug` gets **77 of 77 tasks executed** and fails at exactly
one task, `:app:processDebugResources`:

```
AAPT2 …-linux Daemon #0: Unexpected error output: …/aapt2: 1: Syntax error: "(" unexpected
> Task :app:processDebugResources FAILED
```

Everything else — Java compilation, the Capacitor library builds, manifest
processing, dependency resolution — succeeds. The wrapper itself is not the
problem; only resource compilation is.

Dead ends already checked, so nobody re-checks them:

- Ubuntu's `android-sdk-build-tools` (arm64) is a 2.9 KB metapackage — no aapt2.
  Its `aapt` package is aapt **v1**, which AGP 8.x cannot use.
- Docker is installed and usable without sudo, but **cannot run amd64 images**:
  `docker run --platform linux/amd64 alpine uname -m` → `exec format error`.
  No qemu handler is registered in `/proc/sys/fs/binfmt_misc`.

### Ways to actually get an APK

1. **Build in CI — the supported path.** See below. GitHub Actions runners are
   x86-64, and no local system changes are needed.
2. **Register qemu emulation, then build locally.** One-time, system-wide, and
   root-equivalent (it writes kernel binfmt handlers):
   ```bash
   docker run --privileged --rm tonistiigi/binfmt --install amd64
   ```
   After that, `docker run --platform linux/amd64` works and the build can run
   in an amd64 container. Resource compilation is emulated, so it is slow.
3. **Build on an x86-64 machine** on the tailnet.

## Building the APK in CI

`.github/workflows/android-apk.yml` is `workflow_dispatch`-only:

```bash
gh workflow run android-apk.yml --ref feat/android-capacitor-app
gh run watch
gh run download -n boto-trading-debug-apk
```

The APK it produces is **generic — it contains no backend address**. This is
deliberate: this repository is public, and both workflow inputs and build
artifacts are world-readable, so a baked-in tailnet URL would be published. A CI
step greps the finished APK to enforce that.

Transfer the APK to the phone and open it (Android will ask you to allow
installing from unknown sources). On first launch the app shows a setup screen
asking for the backend address — enter your tailnet URL, e.g.
`http://your-host.your-tailnet.ts.net:8899`, and it is stored on the device.
Then open **Settings** in the app and paste your `VIBE_TRADING_API_KEY`.

Note that `adb` is also x86-64 here, so installing over USB from this machine
needs the same emulation — or just copy the APK to the phone and tap it.

## Backend setup

Bind to the Tailscale IP — **not** `0.0.0.0`, **not** loopback:

```bash
export VIBE_TRADING_API_KEY="$(openssl rand -hex 32)"   # save this, you enter it on the phone
export CORS_ORIGINS="http://localhost,http://localhost:5173,http://127.0.0.1:5173"
# API_ALLOWED_HOSTS: leave unset — see "Do not use tailscale serve" above

python agent/api_server.py --host YOUR.TAILNET.IP.ADDR --port 8899
```

`http://localhost` in `CORS_ORIGINS` is the Capacitor WebView's own origin, set
by `androidScheme: "http"` in `capacitor.config.json`. Without it the browser
blocks every cross-origin request from the app.

## Build and install

```bash
cd android-app
npm install

export JAVA_HOME="$HOME/tools/jdk-21.0.12+8"
export ANDROID_HOME="$HOME/Android/Sdk"

BOTO_API_BASE=http://YOUR-HOST.YOUR-TAILNET.ts.net:8899 npm run apk
```

`BOTO_API_BASE` is **optional**. Setting it bakes the address in and skips the
first-run setup screen — convenient for a local build, but never do it for an
artifact that will be published. Find your value with `tailscale status`.

On an x86-64 machine the APK lands at
`android/app/build/outputs/apk/debug/app-debug.apk` — on this one, see the
aarch64 section above.

Install it — the phone must be on the same tailnet:

```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
# or copy the APK to the phone and open it (requires "install unknown apps")
```

Then open **Settings** in the app and paste the `VIBE_TRADING_API_KEY` value. It
is stored in `localStorage` and sent as `Authorization: Bearer …`.

### Scripts

| Command | Does |
|---|---|
| `npm run build` | Builds `frontend/`, assembles `www/`, injects the shim |
| `npm run sync` | The above, then `cap sync android` |
| `npm run apk` | The above, then Gradle `assembleDebug` |
| `npm run open` | Opens the project in Android Studio |

`BOTO_SKIP_FRONTEND_BUILD=1` reuses the existing `frontend/dist` instead of
rebuilding — useful when only changing the API base.

## Changing the API base without rebuilding

The baked-in value can be overridden on-device. In `chrome://inspect` →
inspect the WebView → console:

```js
__botoGetApiBase()                                    // current value
__botoSetApiBase("http://other-host.YOUR-TAILNET.ts.net:8899")   // set + reload
```

## Upgrading to TLS (removes the cleartext exemption)

```bash
tailscale cert YOUR-HOST.YOUR-TAILNET.ts.net
python agent/api_server.py --host YOUR.TAILNET.IP.ADDR --port 8899 \
  --ssl-keyfile YOUR-HOST.YOUR-TAILNET.ts.net.key \
  --ssl-certfile YOUR-HOST.YOUR-TAILNET.ts.net.crt
```

Then set `androidScheme` back to `"https"`, use an `https://` `BOTO_API_BASE`,
and delete both `<domain-config>` blocks from the network security config. Note
that `api_server.py` does not currently forward `--ssl-*` to `uvicorn.run()`, so
this path needs either a small local patch or running uvicorn directly.

## Regenerating the native project

`android/` is generated by `npx cap add android`. If you delete and regenerate
it, two edits must be reapplied (they are not produced by Capacitor):

1. `android/app/src/main/res/xml/network_security_config.xml` — recreate it.
2. `android/app/src/main/AndroidManifest.xml` — set
   `android:networkSecurityConfig="@xml/network_security_config"` and
   `android:allowBackup="false"` on `<application>`.

## Tailnet names

Replace these if your tailnet differs — they appear in the network security
config, this README, and the `BOTO_API_BASE` you pass at build time:

- Backend host: `YOUR-HOST.YOUR-TAILNET.ts.net` (`YOUR.TAILNET.IP.ADDR`)
- Tailnet domain: `YOUR-TAILNET.ts.net`
