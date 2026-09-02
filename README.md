# YNAB MCP Server

An MCP server that connects AI assistants to your [YNAB](https://www.ynab.com/) budget. Ask your budget questions YNAB can't answer.

**[mcp-ynab.com](https://mcp-ynab.com)** — Full setup guide, troubleshooting, and more.

## Features

- **30+ tools** — budgets, accounts, transactions, categories, payees, months, scheduled transactions, and analytics
- **Delta sync** — only fetches what changed since the last call (uses YNAB's server knowledge)
- **4-tier caching** — TTL cache, delta sync, retry with backoff, SQLite persistence
- **Search & analytics** — text search across transactions, per-category spending breakdowns, Sankey flow data
- **Bulk operations** — create or update multiple transactions in a single call
- **Dollar amounts** — accepts dollars in parameters, converts to YNAB milliunits internally

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
| **Payees** | `list_payees`, `get_payee`, `update_payee` |
| **Payee Locations** | `list_payee_locations`, `get_payee_location`, `get_payee_locations_by_payee` |
| **Months** | `list_months`, `get_month` |
| **Money Movements** | `list_money_movements`, `get_money_movements_for_month`, `list_money_movement_groups`, `get_money_movement_groups_for_month` |
| **Transactions** | `list_transactions`, `get_transaction`, `get_transactions_by_account`, `get_transactions_by_category`, `get_transactions_by_month`, `get_transactions_by_payee`, `search_transactions`, `create_transaction`, `create_transactions`, `update_transaction`, `update_transactions`, `delete_transaction`, `import_transactions` |
| **Scheduled** | `list_scheduled_transactions`, `get_scheduled_transaction`, `create_scheduled_transaction`, `update_scheduled_transaction`, `delete_scheduled_transaction` |
| **Analytics** | `get_money_flow`, `get_spending_by_category` |

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
than a local stdio process), `worker/` deploys the same Python server, unchanged,
behind a Cloudflare Container and a small routing Worker, at
`https://budget.bryanfawcett.com/mcp`.

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

**One-time setup:**

1. Make sure `budget.bryanfawcett.com` has a proxied (orange-clouded) DNS
   record in the `bryanfawcett.com` zone on Cloudflare — a [Route](https://developers.cloudflare.com/workers/configuration/routing/routes/)
   (as opposed to a [Custom Domain](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/))
   only intercepts the `/mcp*` path, so whatever else serves that subdomain
   today keeps serving everything else. If there's no DNS record yet, add a
   proxied placeholder (e.g. an `AAAA` record to `100::`) first.
2. Generate a long random token for `MCP_AUTH_TOKEN` — it's the only thing
   gating access to your YNAB data once the endpoint is public, e.g.:
   ```bash
   openssl rand -hex 32
   ```
3. Requires a Workers **Paid** plan (Containers require it) and, for the
   Docker-build step below, either [Docker](https://docs.docker.com/get-started/get-docker/)
   locally or Cloudflare's own build environment — pick one:

   **Option A — deploy from your machine:**
   ```bash
   cd worker
   npm install
   npx wrangler secret put YNAB_API_KEY
   npx wrangler secret put MCP_AUTH_TOKEN
   npx wrangler deploy
   ```
   (Secrets aren't read from `wrangler.jsonc` — see the [Container secrets guide](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/).
   `wrangler deploy` builds the image via your local Docker.)

   **Option B — connect the repo in the Cloudflare dashboard (Workers Builds),
   so it deploys on every push instead:**
   1. Create a Worker named exactly `ynab-mcp` (must match `"name"` in
      `worker/wrangler.jsonc`, or the build fails), then go to its
      **Settings → Builds → Connect** and pick this GitHub repo.
   2. Set **Root directory** to `worker` — Cloudflare's git-integration builds
      a Dockerfile only when it's under the configured root directory, which
      is why it lives at `worker/Dockerfile` rather than the repo root.
   3. Leave **Deploy command** as the default `npx wrangler deploy`.
   4. Under the Worker's **Settings → Variables & Secrets**, add
      `YNAB_API_KEY` and `MCP_AUTH_TOKEN` as secrets (same two values as
      Option A).
   5. Push to the production branch to trigger the first build — it can take
      several minutes while Cloudflare provisions the container image.
4. In Claude web (**Settings → Connectors → Add custom connector**), use
   `https://budget.bryanfawcett.com/mcp?token=<MCP_AUTH_TOKEN>` as the URL —
   as of this writing, Claude.ai's custom connector UI only has fields for
   OAuth (Authorization/Token URL, Client ID/Secret), not a static header
   ([anthropics/claude-ai-mcp#112](https://github.com/anthropics/claude-ai-mcp/issues/112)),
   so the token travels as a query parameter instead. `src/server/http.py`
   accepts either form; if you're adding this to a client that *does* support
   custom headers (Claude Code, an MCP Inspector, etc.), prefer
   `Authorization: Bearer <MCP_AUTH_TOKEN>` there.

The container's SQLite cache lives on ephemeral disk and rebuilds itself after
a cold start (same cache the stdio transport uses); nothing to configure
there. See `CLAUDE.md` for the day-to-day commands.

## License

[AGPL-3.0](LICENSE)
