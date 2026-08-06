#!/usr/bin/env node
/**
 * Assemble the Capacitor web root from the upstream frontend build.
 *
 * Deliberately does not modify anything under ../frontend: it runs that
 * project's own ``npm run build`` unchanged, copies the output here, and injects
 * the API-base shim into the copy. ../frontend therefore stays byte-identical
 * to the pinned upstream snapshot (see AGENT-BRIEF.md).
 */
import { execFileSync } from "node:child_process";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(here, "..", "frontend");
const distDir = path.join(frontendDir, "dist");
const wwwDir = path.join(here, "www");
const shimSource = path.join(here, "shim", "api-base.js");

const apiBase = (process.env.BOTO_API_BASE || "").replace(/\/+$/, "");

if (apiBase && !/^https?:\/\//.test(apiBase)) {
  console.error(`\nBOTO_API_BASE must start with http:// or https:// (got: ${apiBase})\n`);
  process.exit(1);
}

if (apiBase) {
  console.log(`→ API base: ${apiBase}`);
} else {
  // Deliberate for CI: an APK built from a public repository must not carry a
  // private tailnet address, and workflow artifacts are world-readable. The
  // shim asks for the URL on first launch and stores it on the device instead.
  console.log("→ API base: not baked in — the app will ask on first launch");
}

if (process.env.BOTO_SKIP_FRONTEND_BUILD !== "1") {
  console.log("→ Building upstream frontend (npm run build in ../frontend)");
  execFileSync("npm", ["run", "build"], { cwd: frontendDir, stdio: "inherit" });
}

if (!existsSync(distDir)) {
  console.error(`\nExpected build output at ${distDir} but it does not exist.\n`);
  process.exit(1);
}

console.log("→ Copying dist/ → www/");
await rm(wwwDir, { recursive: true, force: true });
await mkdir(wwwDir, { recursive: true });
await cp(distDir, wwwDir, { recursive: true });

console.log("→ Injecting API-base shim");
const shim = (await readFile(shimSource, "utf8")).replace("__BOTO_API_BASE__", apiBase);
await writeFile(path.join(wwwDir, "api-base.js"), shim, "utf8");

const indexPath = path.join(wwwDir, "index.html");
const html = await readFile(indexPath, "utf8");

if (html.includes("api-base.js")) {
  console.log("  (shim tag already present)");
} else if (!html.includes("</head>")) {
  console.error("\nCould not find </head> in the built index.html; shim not injected.\n");
  process.exit(1);
} else {
  // Classic script at the top of <head>: it executes during parsing, whereas
  // the app's type="module" bundle is deferred to DOMContentLoaded. The patched
  // fetch/EventSource are therefore installed before any app code evaluates.
  await writeFile(
    indexPath,
    html.replace("<head>", '<head>\n    <script src="/api-base.js"></script>'),
    "utf8"
  );
}

console.log(`\n✓ Web root ready at ${wwwDir}`);
console.log("  Next: npx cap sync android\n");
