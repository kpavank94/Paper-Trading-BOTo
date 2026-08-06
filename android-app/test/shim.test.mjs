/**
 * Tests for shim/api-base.js — run with: node --test test/
 *
 * The shim is a browser IIFE, so each case builds a minimal window/global
 * stand-in, substitutes the build-time placeholder, and evaluates it the way
 * index.html would.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
const shimSource = await readFile(path.join(here, "..", "shim", "api-base.js"), "utf8");

const APP_ORIGIN = "http://localhost";
const BACKEND = "http://backend.example.ts.net:8899";

/** Minimal DOM stand-in — just enough for the first-run setup screen. */
function fakeDocument() {
  const created = [];
  function makeElement(tag) {
    const el = {
      tagName: tag,
      children: [],
      style: "",
      textContent: "",
      listeners: {},
      setAttribute(name, value) {
        if (name === "style") this.style = value;
      },
      appendChild(child) {
        this.children.push(child);
      },
      addEventListener(name, fn) {
        this.listeners[name] = fn;
      },
      focus() {},
    };
    created.push(el);
    return el;
  }
  return {
    readyState: "complete",
    body: makeElement("body"),
    createElement: makeElement,
    addEventListener() {},
    created,
  };
}

/** Evaluate the shim against a fake window; return the sandbox plus call log. */
function loadShim({ base = BACKEND, stored = null, capacitor = false } = {}) {
  const calls = { fetch: [], eventSource: [] };

  class FakeEventSource {
    constructor(url, config) {
      this.url = url;
      this.config = config;
      calls.eventSource.push(url);
    }
  }

  const store = new Map();
  if (stored) store.set("boto_api_base_override", stored);

  const doc = fakeDocument();
  const window = {
    document: doc,
    location: { origin: APP_ORIGIN, reload() {} },
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, v),
      removeItem: (k) => store.delete(k),
    },
    fetch(input) {
      calls.fetch.push(typeof input === "string" ? input : input.url);
      return Promise.resolve({ ok: true });
    },
    EventSource: FakeEventSource,
  };
  if (capacitor) window.Capacitor = {};

  const sandbox = { window, URL, Request: undefined, console };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(shimSource.replace("__BOTO_API_BASE__", base), sandbox);

  return { window, calls, doc };
}

test("rewrites root-relative fetch paths to the backend", async () => {
  const { window, calls } = loadShim();
  await window.fetch("/sessions");
  await window.fetch("/auth/sse-ticket");
  assert.deepEqual(calls.fetch, [`${BACKEND}/sessions`, `${BACKEND}/auth/sse-ticket`]);
});

test("rewrites URLs already resolved against the app origin", async () => {
  const { window, calls } = loadShim();
  await window.fetch(`${APP_ORIGIN}/swarm/runs/abc/events`);
  assert.deepEqual(calls.fetch, [`${BACKEND}/swarm/runs/abc/events`]);
});

test("leaves absolute off-origin URLs untouched", async () => {
  const { window, calls } = loadShim();
  await window.fetch("https://example.com/thing");
  await window.fetch("//cdn.example.com/thing");
  assert.deepEqual(calls.fetch, ["https://example.com/thing", "//cdn.example.com/thing"]);
});

test("rewrites EventSource URLs, including ticketed SSE streams", () => {
  const { window, calls } = loadShim();
  new window.EventSource("/swarm/runs/abc/events?ticket=xyz");
  assert.deepEqual(calls.eventSource, [`${BACKEND}/swarm/runs/abc/events?ticket=xyz`]);
});

test("EventSource keeps its readyState constants", () => {
  const { window } = loadShim();
  assert.equal(window.EventSource.CONNECTING, 0);
  assert.equal(window.EventSource.OPEN, 1);
  assert.equal(window.EventSource.CLOSED, 2);
});

test("a localStorage override wins over the build-time base", async () => {
  const override = "http://other.example.ts.net:9000";
  const { window, calls } = loadShim({ stored: override });
  await window.fetch("/sessions");
  assert.deepEqual(calls.fetch, [`${override}/sessions`]);
  assert.equal(window.__botoGetApiBase(), override);
});

test("trailing slashes on the base are normalised away", async () => {
  const { window, calls } = loadShim({ base: `${BACKEND}/` });
  await window.fetch("/sessions");
  assert.deepEqual(calls.fetch, [`${BACKEND}/sessions`]);
});

test("an unsubstituted placeholder leaves fetch untouched", async () => {
  // Guards the web build: if the shim ships without a base, same-origin
  // behaviour must be preserved rather than producing a broken URL.
  const { window, calls } = loadShim({ base: "__BOTO_API_BASE__" });
  await window.fetch("/sessions");
  assert.deepEqual(calls.fetch, ["/sessions"]);
});

test("no base in the web build renders no setup screen", async () => {
  // Outside Capacitor the page is served by the backend itself, so same-origin
  // requests already work and the prompt would be wrong.
  const { doc } = loadShim({ base: "" });
  assert.equal(doc.body.children.length, 0);
});

test("no base inside Capacitor renders the first-run setup screen", () => {
  const { doc } = loadShim({ base: "", capacitor: true });
  assert.equal(doc.body.children.length, 1);
  const text = doc.created.map((el) => el.textContent).join(" ");
  assert.match(text, /Connect to your backend/);
  assert.match(text, /Connect/);
});

test("the setup screen rejects a URL without a scheme", () => {
  const { doc } = loadShim({ base: "", capacitor: true });
  const input = doc.created.find((el) => el.tagName === "input");
  const button = doc.created.find((el) => el.tagName === "button");
  const error = doc.created.find((el) => el.style.includes("#f87171"));

  input.value = "my-host.example.ts.net:8899"; // no http://
  button.listeners.click();
  assert.match(error.textContent, /must start with http/i);
});

test("the setup screen stores a valid URL and reloads", () => {
  let reloaded = false;
  const { window, doc } = loadShim({ base: "", capacitor: true });
  window.location.reload = () => {
    reloaded = true;
  };
  const input = doc.created.find((el) => el.tagName === "input");
  const button = doc.created.find((el) => el.tagName === "button");

  input.value = "http://my-host.example.ts.net:8899/";
  button.listeners.click();

  // Trailing slash normalised, persisted, and the app restarted so the patched
  // primitives pick the value up.
  assert.equal(window.__botoGetApiBase(), "");
  assert.equal(
    window.localStorage.getItem("boto_api_base_override"),
    "http://my-host.example.ts.net:8899"
  );
  assert.equal(reloaded, true);
});
