/**
 * Capacitor runtime shim — rewrites same-origin API calls to the backend.
 *
 * The upstream SPA sets ``BASE = ""`` in ``src/lib/api.ts`` and writes every
 * request as a root-relative path (``/sessions``, ``/swarm/runs/...``). In a
 * browser that works because Vite proxies those paths to the API on the same
 * origin. Inside the Android WebView the app is served from ``https://localhost``
 * by Capacitor, so those same paths would resolve to the WebView itself and
 * never reach the backend.
 *
 * Rather than patch ``api.ts`` — which would drop it out of the byte-identical
 * upstream set this repo tracks (see AGENT-BRIEF.md) — this shim patches the two
 * networking primitives the app actually uses, ``fetch`` and ``EventSource``,
 * before the app bundle evaluates. It is injected as a classic script in
 * ``<head>``; classic scripts run before deferred module bundles, so the patch
 * is always in place by the time React mounts.
 *
 * The build-time default below is replaced by build.mjs. It can be overridden
 * on-device via ``__botoSetApiBase(url)`` so a changed tailnet address does not
 * require a rebuild.
 */
(function () {
  "use strict";

  var BUILD_BASE = "__BOTO_API_BASE__";
  var STORAGE_KEY = "boto_api_base_override";

  function trimSlashes(value) {
    return String(value || "").replace(/\/+$/, "");
  }

  function resolveBase() {
    try {
      var override = window.localStorage.getItem(STORAGE_KEY);
      if (override) return trimSlashes(override);
    } catch (err) {
      /* localStorage can throw when storage is partitioned or disabled */
    }
    return trimSlashes(BUILD_BASE);
  }

  var BASE = resolveBase();

  // Exposed for on-device reconfiguration from the WebView console or a
  // future settings hook. Reloads so the patched primitives pick up the change.
  window.__botoGetApiBase = function () {
    return BASE;
  };
  window.__botoSetApiBase = function (value) {
    window.localStorage.setItem(STORAGE_KEY, trimSlashes(value));
    window.location.reload();
  };

  // Unconfigured: the APK ships without a baked-in backend URL so that CI
  // artifacts carry no private network identifiers. Ask for it once, on device,
  // and store it. Same-origin behaviour is left intact for the plain web build,
  // which is served by the backend itself and needs no rewriting.
  if (!BASE || BASE.indexOf("__BOTO_API_BASE__") !== -1) {
    if (window.Capacitor) promptForApiBase();
    return;
  }

  /**
   * First-run setup: a minimal, dependency-free screen asking where the backend
   * lives. Rendered directly into the document rather than as a React view so it
   * needs nothing from the app bundle — and so no upstream file has to change.
   */
  function promptForApiBase() {
    function render() {
      var overlay = window.document.createElement("div");
      overlay.setAttribute("style", [
        "position:fixed", "inset:0", "z-index:2147483647",
        "display:flex", "align-items:center", "justify-content:center",
        "padding:24px", "background:#0b0f19", "color:#e5e7eb",
        "font:16px/1.5 system-ui,-apple-system,sans-serif",
      ].join(";"));

      var card = window.document.createElement("div");
      card.setAttribute("style", "width:100%;max-width:420px");

      var title = window.document.createElement("h1");
      title.textContent = "Connect to your backend";
      title.setAttribute("style", "margin:0 0 8px;font-size:20px;font-weight:600");

      var help = window.document.createElement("p");
      help.textContent =
        "Enter the Tailscale address of the machine running the API. " +
        "Find it with `tailscale status`.";
      help.setAttribute("style", "margin:0 0 20px;color:#9ca3af;font-size:14px");

      var input = window.document.createElement("input");
      input.type = "url";
      input.placeholder = "http://your-host.your-tailnet.ts.net:8899";
      input.setAttribute("autocapitalize", "none");
      input.setAttribute("autocorrect", "off");
      input.setAttribute("style", [
        "width:100%", "box-sizing:border-box", "padding:12px 14px",
        "border:1px solid #374151", "border-radius:8px",
        "background:#111827", "color:#e5e7eb", "font-size:16px",
      ].join(";"));

      var error = window.document.createElement("p");
      error.setAttribute("style", "margin:8px 0 0;color:#f87171;font-size:14px;min-height:20px");

      var button = window.document.createElement("button");
      button.textContent = "Connect";
      button.setAttribute("style", [
        "width:100%", "margin-top:16px", "padding:12px",
        "border:0", "border-radius:8px", "background:#2563eb", "color:#fff",
        "font-size:16px", "font-weight:600", "cursor:pointer",
      ].join(";"));

      function submit() {
        var value = trimSlashes(input.value);
        if (!/^https?:\/\/.+/.test(value)) {
          error.textContent = "Must start with http:// or https://";
          return;
        }
        window.__botoSetApiBase(value);
      }

      button.addEventListener("click", submit);
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") submit();
      });

      card.appendChild(title);
      card.appendChild(help);
      card.appendChild(input);
      card.appendChild(error);
      card.appendChild(button);
      overlay.appendChild(card);
      window.document.body.appendChild(overlay);
      input.focus();
    }

    if (window.document.readyState === "loading") {
      window.document.addEventListener("DOMContentLoaded", render);
    } else {
      render();
    }
  }

  var ORIGIN_PREFIX = window.location.origin + "/";

  /** Point a root-relative or app-origin URL at the backend; leave others alone. */
  function absolutize(url) {
    if (typeof url !== "string") return url;
    // Protocol-relative (``//host/path``) is already off-origin.
    if (url.slice(0, 2) === "//") return url;
    if (url.charAt(0) === "/") return BASE + url;
    // Already resolved against the WebView origin (e.g. a Request object's .url).
    if (url.indexOf(ORIGIN_PREFIX) === 0) {
      return BASE + url.slice(window.location.origin.length);
    }
    return url;
  }

  var originalFetch = window.fetch;
  if (typeof originalFetch === "function") {
    window.fetch = function (input, init) {
      if (typeof input === "string") {
        return originalFetch.call(this, absolutize(input), init);
      }
      if (typeof URL !== "undefined" && input instanceof URL) {
        return originalFetch.call(this, absolutize(input.href), init);
      }
      if (typeof Request !== "undefined" && input instanceof Request) {
        var rewritten = absolutize(input.url);
        if (rewritten !== input.url) {
          return originalFetch.call(this, new Request(rewritten, input), init);
        }
      }
      return originalFetch.call(this, input, init);
    };
  }

  var OriginalEventSource = window.EventSource;
  if (typeof OriginalEventSource === "function") {
    var PatchedEventSource = function (url, config) {
      return new OriginalEventSource(absolutize(String(url)), config);
    };
    PatchedEventSource.prototype = OriginalEventSource.prototype;
    PatchedEventSource.CONNECTING = 0;
    PatchedEventSource.OPEN = 1;
    PatchedEventSource.CLOSED = 2;
    window.EventSource = PatchedEventSource;
  }
})();
