# YNAB MCP Server

An MCP server that connects AI assistants to your [YNAB](https://www.ynab.com/) budget. Ask your budget questions YNAB can't answer.

**[mcp-ynab.com](https://mcp-ynab.com)** — Full setup guide, troubleshooting, and more.

## Features

- **50+ tools** — budgets, accounts, transactions, categories, payees, months, scheduled transactions, analytics, and reconciliation
- **Delta sync** — only fetches what changed since the last call (uses YNAB's server knowledge)
- **4-tier caching** — TTL cache, delta sync, retry with backoff, SQLite persistence
- **Search & analytics** — text search across transactions, per-category spending breakdowns, Sankey flow data
- **Monthly reports with a live dashboard** — `get_monthly_report` returns income/spending summary, category and payee breakdowns, overspent categories, and a multi-month trend in one call. On hosts that support [MCP Apps](https://github.com/modelcontextprotocol/ext-apps) (Claude, ChatGPT), it renders as an interactive dashboard (KPI tiles, charts, tables) automatically — no separate artifact step needed. On other hosts, the same data comes back as plain JSON.
- **Reconciliation** — `reconcile_account` compares an account's cleared transactions against a real-world statement balance, previews the adjustment and which transactions would be marked reconciled, and (once confirmed) applies it — the same workflow as YNAB's own "Reconcile" button. `export_transactions_csv` exports a register (any account, date range, cleared status) as CSV for reviewing against a statement.
- **Bulk operations** — create or update multiple transactions in a single call
- **Dollar amounts** — accepts dollars in parameters, converts to YNAB milliunits internally
- **Icons** — the server and every tool carry an on-brand icon (SEP for `icons`) for clients that render them

## Quick Start

```
uv tool run mcp-ynab
```

Requires a [YNAB personal access token](https://app.ynab.com/settings/developer) set as `YNAB_API_KEY`.

## Configuration

### Claude Desktop / ChatGPT

Add to your config file:

```json
{
  "mcpServers": {
    "ynab": {
      "command": "uv",
      "args": ["tool", "run", "mcp-ynab"],
      "env": {
        "YNAB_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add-json ynab --scope user '{"type":"stdio","command":"uv","args":["tool","run","mcp-ynab"],"env":{"YNAB_API_KEY":"your-api-key-here"}}'
```

See [mcp-ynab.com](https://mcp-ynab.com) for config file locations and troubleshooting.

## Available Tools

| Group | Tools |
|-------|-------|
| **User** | `get_user` |
| **Plans** | `list_plans`, `get_plan`, `get_plan_settings` |
| **Accounts** | `list_accounts`, `get_account`, `create_account` |
| **Categories** | `list_categories`, `get_category`, `create_category`, `update_category`, `create_category_group`, `update_category_group`, `get_category_for_month`, `update_category_for_month` |
| **Payees** | `list_payees`, `create_payee`, `get_payee`, `update_payee` |
| **Payee Locations** | `list_payee_locations`, `get_payee_location`, `get_payee_locations_by_payee` |
| **Months** | `list_months`, `get_month` |
| **Money Movements** | `list_money_movements`, `get_money_movements_for_month`, `list_money_movement_groups`, `get_money_movement_groups_for_month` |
| **Transactions** | `list_transactions`, `get_transaction`, `get_transactions_by_account`, `get_transactions_by_category`, `get_transactions_by_month`, `get_transactions_by_payee`, `search_transactions`, `create_transaction`, `create_transactions`, `update_transaction`, `update_transactions`, `delete_transaction`, `import_transactions` |
| **Scheduled** | `list_scheduled_transactions`, `get_scheduled_transaction`, `create_scheduled_transaction`, `update_scheduled_transaction`, `delete_scheduled_transaction` |
| **Analytics** | `get_money_flow`, `get_spending_by_category`, `get_monthly_report` |
| **Reconciliation** | `export_transactions_csv`, `reconcile_account` |

### Field selection

Every tool that returns a model accepts an optional `exclude_fields` list. By
default each tool returns a sensible subset of fields to keep token usage low.
See [FIELDS.md](./FIELDS.md) for per-model defaults and override examples.

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run server standalone
uv run python -m src.server
```

Requires `YNAB_API_KEY` in `.env.local` for running the server.

## Remote deployment (Cloudflare Container + Worker)

For connecting Claude web (or any client that needs a remote MCP server rather
than a local stdio process), `worker/` deploys the same Python server,
unchanged, behind a Cloudflare Container and a small routing Worker, on a
subdomain of your choosing — e.g. this fork's own instance runs at
`https://ynab.nyuchi.com/mcp`, but nothing below is tied to that
domain or account. Fork this repo, point the pieces below at your own domain
and Cloudflare account, and you have your own private remote instance.

The Python server itself just gained a second transport
(`src/server/http.py`, streamable-http instead of stdio); `worker/Dockerfile`
containerizes it, and `worker/src/index.ts` is a ~15-line Worker that forwards
requests into that container. Nothing about the stdio/Claude Desktop setup
above changes. (The Dockerfile lives under `worker/` rather than the repo
root, with `image_build_context: ".."` in `wrangler.jsonc` pointing the actual
build context back at the repo root — Cloudflare's Workers Builds
git-integration requires the Wrangler config and Dockerfile to share a root
directory, and this keeps both deploy paths below working from the same
layout.)

**Single-tenant vs. multi-tenant:** by default this deploys as a *single-tenant*
server — one `YNAB_API_KEY` secret for the whole deployment, gated by a
separate `MCP_AUTH_TOKEN` shared secret. That's the right choice for a
private instance you're deploying just for yourself. If you want other
people to be able to use your deployment too — each with their own YNAB
budget, not yours — set `MCP_MULTI_TENANT=true` instead (see step 1 below):
there's then no `YNAB_API_KEY`/`MCP_AUTH_TOKEN` at all, and each caller's
bearer token/`?token=` value *is* their own [YNAB personal access
token](https://app.ynab.com/settings/developer), used only for their own
requests. `src/server/http.py` keeps every caller's YNAB client, response
cache, and delta-sync state (a separate SQLite file per caller, under the
same cache directory) completely separate — nobody using a multi-tenant
deployment can see anyone else's budget, including yours. On top of that,
`worker/src/index.ts` routes each caller to their own container instance in
this mode (keyed by a hash of their token), so tenants also get independent
CPU/memory and each container sleeps on its own idle timer instead of
sharing one — one busy tenant can't keep another tenant's container running
(`containers[0].max_instances` in `wrangler.jsonc` caps how many can be
alive at once; raise it if you expect more concurrent users).

**Before your first deploy**, edit `worker/wrangler.jsonc` for your own setup:

- `name` — the Worker's name in your Cloudflare account. Whatever you pick
  here is also what you'll name the Worker in the dashboard (Option B below
  checks that the two match).
- `routes[0].pattern` — your own subdomain (e.g. `mcp.yourdomain.com`)
  instead of `ynab.nyuchi.com`. This repo declares it as a [Custom
  Domain](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)
  rather than a path-scoped [Route](https://developers.cloudflare.com/workers/configuration/routing/routes/),
  on the assumption that the Worker is the only thing on that subdomain —
  Cloudflare then manages the DNS record and certificate for it
  automatically, no DNS setup needed. If you'd rather share the subdomain
  with something else, switch this to a Route scoped to `/mcp*` instead.

**One-time setup:**

1. Decide single-tenant (default) or multi-tenant, and prepare the secrets
   for whichever you picked:
   - **Single-tenant:** generate a long random token for `MCP_AUTH_TOKEN` —
     it's the only thing gating access to your YNAB data once the endpoint
     is public, e.g.:
     ```bash
     openssl rand -hex 32
     ```
     You'll set this and `YNAB_API_KEY` as secrets below.
   - **Multi-tenant:** nothing to generate — you'll set `MCP_MULTI_TENANT=true`
     as a secret below instead of `YNAB_API_KEY`/`MCP_AUTH_TOKEN`, and each
     caller brings their own YNAB token.
2. Requires a Workers **Paid** plan (Containers require it) and, for the
   Docker-build step below, either [Docker](https://docs.docker.com/get-started/get-docker/)
   locally or Cloudflare's own build environment — pick one:

   **Option A — deploy from your machine:**
   ```bash
   cd worker
   npm install
   npx wrangler secret put YNAB_API_KEY      # single-tenant only
   npx wrangler secret put MCP_AUTH_TOKEN    # single-tenant only
   npx wrangler secret put MCP_MULTI_TENANT  # multi-tenant only — value: true
   npm run deploy
   ```
   (Secrets aren't read from `wrangler.jsonc` — see the [Container secrets guide](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/).
   `npm run deploy` builds the Astro site in `worker/site` first, then runs
   `wrangler deploy`, which builds the container image via your local Docker.)

   **Option B — connect your fork in the Cloudflare dashboard (Workers
   Builds), so it deploys automatically on every push to `main`:**
   1. Create a Worker with the same name you set in `worker/wrangler.jsonc`'s
      `"name"` field (they must match, or the build fails), then go to its
      **Settings → Builds → Connect** and pick your fork of this repo.
   2. Set **Root directory** to `worker` — Cloudflare's git-integration builds
      a Dockerfile only when it's under the configured root directory, which
      is why it lives at `worker/Dockerfile` rather than the repo root.
   3. Set **Build command** to `npm run build:site` — this builds the Astro
      landing page/privacy policy (`worker/site`) into `worker/site/dist`,
      which `wrangler.jsonc`'s `assets` binding serves; without this step the
      deploy command below would upload an empty (or stale) assets directory.
      Leave **Deploy command** as the default `npx wrangler deploy`.
   4. Set **Production branch** to `main` under **Settings → Builds**. Without
      this, Workers Builds deploys to *production* off of every push to
      *every* branch — including work-in-progress PR branches — rather than
      only after a merge to `main`.
   5. Under the Worker's **Settings → Variables & Secrets**, add either
      `YNAB_API_KEY` and `MCP_AUTH_TOKEN` (single-tenant) or `MCP_MULTI_TENANT`
      set to `true` (multi-tenant) as secrets.
   6. Push to `main` to trigger the first build — it can take several minutes
      while Cloudflare provisions the container image.
4. Connecting a client (**Settings → Connectors → Add custom connector** in
   Claude web) — as of this writing, Claude.ai's custom connector UI only has
   fields for OAuth (Authorization/Token URL, Client ID/Secret), not a static
   header ([anthropics/claude-ai-mcp#112](https://github.com/anthropics/claude-ai-mcp/issues/112)),
   so the token travels as a `?token=` query parameter instead. `src/server/http.py`
   accepts either form; if you're adding this to a client that *does* support
   custom headers (Claude Code, an MCP Inspector, etc.), prefer
   `Authorization: Bearer <token>` there.
   - **Single-tenant:** `https://<your-domain>/mcp?token=<MCP_AUTH_TOKEN>`
   - **Multi-tenant:** `https://<your-domain>/mcp?token=<your-own-YNAB-personal-access-token>`
     — each person uses their own [YNAB personal access
     token](https://app.ynab.com/settings/developer) here, not a value you hand out.

The container's SQLite cache lives on ephemeral disk and rebuilds itself after
a cold start (same cache the stdio transport uses); nothing to configure
there. In multi-tenant mode this is one SQLite file per caller instead of
one shared file — created lazily the first time each caller's token is seen,
and bounded (oldest evicted) so a flood of distinct tokens can't grow it
unbounded. See `CLAUDE.md` for the day-to-day commands.

## License

[AGPL-3.0](LICENSE)
