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
- Or connect `worker/` to this repo via **Workers & Pages → [Worker] → Settings → Builds** in the Cloudflare dashboard, with root directory `worker`, to deploy on every push instead of running `wrangler deploy` locally — see README.md.

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
- **`server/http.py`** — ASGI app exposing the same tools over the MCP SDK's streamable-http transport instead of stdio, gated by a `MCP_AUTH_TOKEN` bearer-token check (the SDK's built-in OAuth auth is overkill for a single-user deployment). Entry point for `worker/Dockerfile`.

### Cloudflare Worker (`worker/`)

A thin TypeScript Worker (`@cloudflare/containers`) that forwards all of `budget.bryanfawcett.com` into a Container built from `worker/Dockerfile` (the container itself only serves `/mcp` and `/health`; anything else 404s). It does not reimplement any server logic — the Python code is unchanged, just given an HTTP transport. `budget.bryanfawcett.com` is declared as a Custom Domain in `wrangler.jsonc` (this Worker is the only thing on that subdomain), not a path-scoped Route, so Cloudflare manages the DNS record and certificate automatically. The Dockerfile lives under `worker/` (not the repo root) because Cloudflare's Workers Builds git-integration requires the Wrangler config and Dockerfile to share a root directory; `image_build_context: ".."` in `wrangler.jsonc` points the actual Docker build context back at the repo root, since the Dockerfile's `COPY` paths (`pyproject.toml`, `src/`, etc.) are root-relative. See README.md's "Remote deployment" section for the one-time secrets setup.

### Key conventions

- **Milliunits:** YNAB stores money as milliunits (1000 = $1.00). The Python server accepts dollars in tool parameters and converts to milliunits internally.
- **Month format:** YNAB months use first-of-month dates (`2026-03-01` for March 2026).
- **Dependency bounds:** runtime deps in `pyproject.toml` carry upper bounds. An unbounded `mcp[cli]>=1.26.0` broke every fresh install when the SDK shipped 2.0.0 (#21). `uv run pytest` uses `uv.lock` and cannot catch this class of break; `python scripts/smoke_test.py` resolves fresh from the declared constraints and can. Run it before releasing, and after touching any dependency.
