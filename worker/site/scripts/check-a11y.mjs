// Accessibility + language audit for the built static site, via axe-core
// against a headless Chromium. Covers WCAG 2 A/AA rules, including
// html-has-lang/html-lang-valid/valid-lang (the "language checks" -- every
// page must declare a correct lang attribute, and any element that switches
// language must mark it) alongside the rest of axe's default ruleset
// (landmarks, alt text, contrast via axe's own algorithm, label
// associations, ARIA usage, and more).
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import { createServer } from "node:http";
import { readFile, readdir } from "node:fs/promises";
import { extname, join, relative as relativePath, sep } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../dist", import.meta.url));
const PAGES = ["/", "/project", "/privacy-policy"];
const MIME = { ".html": "text/html", ".css": "text/css", ".js": "application/javascript", ".svg": "image/svg+xml" };

// Builds a URL-path -> absolute-file-path map by walking `root` once, using
// only the trusted filesystem listing -- never a path built from a request.
// The request handler below does a plain Map lookup, so no request-derived
// value ever reaches a filesystem call; a request for anything not already
// in the manifest just 404s.
async function buildManifest(root) {
  const manifest = new Map();
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
        continue;
      }
      const urlPath = "/" + relativePath(root, full).split(sep).join("/");
      manifest.set(urlPath, full);
      if (entry.name === "index.html") {
        manifest.set(urlPath.slice(0, -"index.html".length) || "/", full);
        manifest.set(urlPath.slice(0, -"/index.html".length) || "/", full);
      }
    }
  }
  await walk(root);
  return manifest;
}

function serveStatic(manifest) {
  return createServer(async (req, res) => {
    const requestPath = decodeURIComponent((req.url || "/").split("?")[0]);
    const file = manifest.get(requestPath);
    if (!file) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    try {
      const body = await readFile(file);
      res.writeHead(200, { "content-type": MIME[extname(file)] || "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end("Not found");
    }
  });
}

async function main() {
  const manifest = await buildManifest(DIST);
  const server = serveStatic(manifest);
  await new Promise((resolve) => server.listen(0, resolve));
  const { port } = server.address();
  const base = `http://localhost:${port}`;

  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined });
  const context = await browser.newContext();
  let failed = false;

  try {
    for (const path of PAGES) {
      const page = await context.newPage();
      await page.goto(base + path, { waitUntil: "networkidle" });
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "best-practice"]).analyze();
      await page.close();

      if (results.violations.length === 0) {
        console.log(`PASS  ${path} — no violations`);
        continue;
      }
      failed = true;
      console.error(`FAIL  ${path} — ${results.violations.length} violation(s)`);
      for (const v of results.violations) {
        console.error(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} node(s))`);
        for (const node of v.nodes.slice(0, 3)) {
          console.error(`      ${node.target.join(" ")}`);
        }
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  if (failed) {
    console.error("\nAccessibility violations found — see above.");
    process.exit(1);
  }
  console.log("\nNo accessibility violations on any page.");
}

main();
