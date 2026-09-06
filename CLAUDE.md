# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Landing Page (Astro):**
- `cd website && npm run dev` — Start dev server
- `cd website && npm run build` — Production build

**Python MCP Server:**
- `uv run pytest` — Run all tests
- `uv run pytest tests/test_foo.py::test_name` — Run a single test
- `uv run python -m src.server` — Run MCP server standalone (stdio transport)
- `YNAB_API_KEY=... MCP_AUTH_TOKEN=... uv run uvicorn src.server.http:app --reload` — Run the streamable-http transport (used by the container deployment) locally

**Environment:** Requires `YNAB_API_KEY` in `.env.local`

**Remote deployment (Cloudflare Container + Worker):**
- `cd worker && docker build -t ynab-mcp .` — Build the container image standalone
- `cd worker && npm install && npx wrangler deploy` — Deploy the Worker + Container to Cloudflare (builds the image via Docker as part of deploy; needs Docker running locally)
- `cd worker && npx wrangler secret put YNAB_API_KEY` / `MCP_AUTH_TOKEN` — Set the two secrets the container needs (see README.md's "Remote deployment" section for the full setup)
- Or connect `worker/` to this repo via **Workers & Pages → [Worker] → Settings → Builds** in the Cloudflare dashboard, with root directory `worker` and **production branch set to `main`**, to deploy on merge instead of running `wrangler deploy` locally — see README.md. (Without a production branch set, every push to every branch deploys to production.)

## Architecture

This repo contains three things:
1. **A Python MCP server** (`src/`) that connects AI assistants to the YNAB API
2. **A landing page** (`website/`) built with Astro + Tailwind, deployed to Vercel
3. **A Cloudflare Worker** (`worker/`) that fronts a Container running the same Python server over HTTP, for remote/Claude-web use

### Python MCP server (`src/`)

- **`server/`** — MCPServer (mcp SDK 2.x) server package, run standalone via `python -m src.server`. Tool definitions are split by domain across submodules (`accounts.py`, `transactions.py`, `categories.py`, etc.) and registered through `src/server/__init__.py`. Shared infrastructure (`mcp`, `cache`, `client`, `handle_errors`, `serialize` helpers, `DEFAULT_EXCLUDES`) lives in `src/server/_shared.py`. All tools use the `@handle_errors` decorator for uniform YNAB/HTTP error handling and lazy DB init.
- **`ynab_client.py`** — Async httpx client for YNAB API v1.
- **`cache/`** — 4-tier caching: TTL-based response cache, delta sync (server knowledge tracking), retry with exponential backoff, SQLite persistence.
- **`models/`** — Pydantic models, each module exports a `*_DEFAULT_EXCLUDE` set defining the fields hidden from MCP responses by default. The registry in `src/server/_shared.py` (`DEFAULT_EXCLUDES`) maps model classes to their default exclude sets. Every MCP tool accepts an optional `exclude_fields: list[str]` param that, when provided, fully replaces the default. See `FIELDS.md` for the per-model field reference.
- **`config.py`** — `Settings` via pydantic-settings. Cache DB path is platform-specific (`~/Library/Application Support/ynab-mcp-server/cache.db` on macOS).
- **`server/http.py`** — ASGI app exposing the same tools over the MCP SDK's streamable-http transport instead of stdio. Entry point for `worker/Dockerfile`. Two modes, via `Settings.multi_tenant` (`MCP_MULTI_TENANT`): single-tenant (default) gates every request behind one static `MCP_AUTH_TOKEN` and uses the one process-wide `YNAB_API_KEY`; multi-tenant treats each request's bearer/query token as *that caller's own* YNAB personal access token, resolving it (via `TenantRegistry`) to a per-caller `YNABClient`/`CacheService`/SQLite file, scoped onto `src.server._shared`'s contextvar-backed `client`/`cache` for the duration of the request — so the ~15 tool modules need no per-tenant awareness at all, they just call `_shared.cache.foo()` as always.
- **`server/dashboard.py`** — MCP Apps (SEP-1865) `ui://` resource: a self-contained HTML/JS dashboard (Chart.js via CDN) linked to `get_monthly_report` through that tool's `meta={"ui": {"resourceUri": ...}}`. Hosts that support MCP Apps render it in a sandboxed iframe instead of showing raw JSON; the app reads `result.content[0].text` (the same JSON every tool already returns) rather than SDK-native `structuredContent`, since giving `get_monthly_report` a schema'd return type for that would conflict with `handle_errors`' plain-string error responses.
- **`server/icons.py`** — one on-brand `Icon` (copper background, white glyph) per tool *domain*, not per tool; passed to every `@_shared.mcp.tool(icons=[...])` call and to `MCPServer(icons=[icons.SERVER])`. `tests/test_icons.py` fails if a tool is ever added without one.
- **`server/reconcile.py`** — `export_transactions_csv` (a register export, any account/date-range/cleared-status, as CSV text) and `reconcile_account` (YNAB's own "Reconcile" workflow: compare cleared transactions against a real-world statement balance, then create an adjustment and mark transactions reconciled). `reconcile_account` defaults to a dry run (`confirm=False`) since marking transactions reconciled is hard to reverse from the API — always preview before passing `confirm=True`.

### Cloudflare Worker (`worker/`)

A thin TypeScript Worker (`@cloudflare/containers`) that forwards all of `budget.bryanfawcett.com` into a Container built from `worker/Dockerfile` (the container itself only serves `/mcp` and `/health`; anything else 404s). It does not reimplement any server logic — the Python code is unchanged, just given an HTTP transport. `budget.bryanfawcett.com` is declared as a Custom Domain in `wrangler.jsonc` (this Worker is the only thing on that subdomain), not a path-scoped Route, so Cloudflare manages the DNS record and certificate automatically. The Dockerfile lives under `worker/` (not the repo root) because Cloudflare's Workers Builds git-integration requires the Wrangler config and Dockerfile to share a root directory; `image_build_context: ".."` in `wrangler.jsonc` points the actual Docker build context back at the repo root, since the Dockerfile's `COPY` paths (`pyproject.toml`, `src/`, etc.) are root-relative. See README.md's "Remote deployment" section for the one-time secrets setup.

**Per-tenant container routing:** in multi-tenant mode, `worker/src/index.ts` routes `/mcp*` requests to a container instance keyed by a hash of the caller's own token (`getContainer(binding, tenantId)`), instead of the single shared instance single-tenant mode uses. Each tenant then gets their own Durable Object/container — independent CPU/memory, independent `sleepAfter` idle timer, one tenant's traffic can't keep another's container warm — genuine per-tenant scale-to-zero, not just the per-process isolation `src/server/http.py`'s `TenantRegistry` already provides (that still applies too, underneath this). `containers[0].max_instances` in `wrangler.jsonc` is 10 for this reason (more than one container can now legitimately be alive at once); raise it if concurrent usage grows past that.

Considered `@cloudflare/sandbox` for this instead of using `@cloudflare/containers` directly — it's built *on top of* the same `Container` class (its own docs: "Extends Cloudflare Container for isolation"), and its `sleepAfter`/per-ID-instance model is the identical underlying mechanism, just re-exposed through an `exec()`/`startProcess()` API meant for running agent-driven or untrusted code, not fronting one purpose-built persistent service. It would add API surface (process startup, port-exposure health-polling, preview-URL tokens) without adding any capability this deployment doesn't already have via `getContainer(binding, id)`. Cloudflare's separate `@cloudflare/think` SDK is for building the LLM-orchestrating agent itself (chat turns, sub-agents, durable execution fibers) — this repo's server is a tool provider *for* an agent, not an agent, so it doesn't apply here either.

### Key conventions

- **Milliunits:** YNAB stores money as milliunits (1000 = $1.00). The Python server accepts dollars in tool parameters and converts to milliunits internally.
- **Month format:** YNAB months use first-of-month dates (`2026-03-01` for March 2026).
- **Dependency bounds:** runtime deps in `pyproject.toml` carry upper bounds. An unbounded `mcp[cli]>=1.26.0` broke every fresh install when the SDK shipped 2.0.0 (#21). `uv run pytest` uses `uv.lock` and cannot catch this class of break; `python scripts/smoke_test.py` resolves fresh from the declared constraints and can. Run it before releasing, and after touching any dependency.
