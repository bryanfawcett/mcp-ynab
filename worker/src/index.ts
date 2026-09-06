import { Container, getContainer } from "@cloudflare/containers";
import { LANDING_PAGE_HTML } from "./landing";

interface Env {
  YNAB_MCP_CONTAINER: DurableObjectNamespace<YnabMcpContainer>;
  // Set with `wrangler secret put`, not in wrangler.jsonc — see README.md.
  // Single-tenant mode (default) needs both; multi-tenant mode needs neither
  // (each caller's own YNAB token travels with their request instead) — so
  // both are declared optional here and only the deployment's chosen mode's
  // secrets need to actually be set.
  YNAB_API_KEY?: string;
  MCP_AUTH_TOKEN?: string;
  MCP_MULTI_TENANT?: string;
}

export class YnabMcpContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "10m";
  envVars = {
    YNAB_API_KEY: this.env.YNAB_API_KEY ?? "",
    MCP_AUTH_TOKEN: this.env.MCP_AUTH_TOKEN ?? "",
    MCP_MULTI_TENANT: this.env.MCP_MULTI_TENANT ?? "",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    // Only /mcp (and /health, for manual poking) goes to the container —
    // everything else is the static landing page, served without waking it.
    if (pathname === "/mcp" || pathname.startsWith("/mcp/") || pathname === "/health") {
      // Every request is routed to the same one container instance — that's
      // still correct in multi-tenant mode, since the Python app itself keeps
      // each caller's YNAB client/cache separate per-request (see
      // src/server/http.py's TenantRegistry), not this routing layer.
      const container = getContainer(env.YNAB_MCP_CONTAINER);
      return container.fetch(request);
    }

    if (pathname === "/") {
      return new Response(LANDING_PAGE_HTML, {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
