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

// Same token extraction as src/server/http.py's _presented_token, so the
// Worker and the Python app agree on what identifies a caller: an
// `Authorization: Bearer <token>` header, falling back to a `?token=` query
// param (for clients, like Claude.ai's custom connector UI, that can only
// supply a URL).
function presentedToken(request: Request): string {
  const auth = request.headers.get("authorization") ?? "";
  const [scheme, token] = auth.split(" ", 2);
  if (scheme?.toLowerCase() === "bearer" && token) return token;
  return new URL(request.url).searchParams.get("token") ?? "";
}

// A stable, non-reversible id for whichever container instance should serve
// this caller — never the raw token itself, so it doesn't sit around as a
// Durable Object name. Two requests with the same token always hash to the
// same id, so a tenant's traffic keeps landing on their own container.
async function tenantContainerId(request: Request): Promise<string | undefined> {
  const token = presentedToken(request);
  if (!token) return undefined;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/mcp" || pathname.startsWith("/mcp/")) {
      // Multi-tenant mode: route each caller's own token to its own
      // container instance — each is a separate Durable Object with its own
      // process, memory, and idle timer (sleepAfter above), so one tenant's
      // traffic can't keep another tenant's container warm, and each one
      // genuinely scales to zero independently. The Python app's own
      // per-tenant isolation (src/server/http.py's TenantRegistry) still
      // applies underneath this — this is about which *container* handles a
      // request, not a replacement for that.
      // Single-tenant mode keeps everyone on the one shared instance,
      // matching its one-account model (and an unauthenticated request, in
      // either mode, falls through to that same shared instance, where the
      // Python app's own auth check rejects it).
      const containerId = env.MCP_MULTI_TENANT === "true" ? await tenantContainerId(request) : undefined;
      const container = getContainer(env.YNAB_MCP_CONTAINER, containerId);
      return container.fetch(request);
    }

    if (pathname === "/health") {
      // Always the shared/default instance — a liveness check isn't tied to
      // any one tenant.
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
