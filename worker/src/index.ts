import { Container, getContainer } from "@cloudflare/containers";

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
  MCP_RATE_LIMITER: RateLimit;
  CF_VERSION_METADATA: WorkerVersionMetadata;
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
// supply a URL). Splits on the first space only (mirroring Python's
// `.partition(" ")`) and never falls back to the query param once the scheme
// is "bearer" — even an empty token after "Bearer" is treated as presented
// (and rejected downstream), not as "no header, try the query param instead".
function presentedToken(request: Request): string {
  const auth = request.headers.get("authorization") ?? "";
  const spaceIndex = auth.indexOf(" ");
  const scheme = spaceIndex === -1 ? auth : auth.slice(0, spaceIndex);
  if (scheme.toLowerCase() === "bearer") {
    return spaceIndex === -1 ? "" : auth.slice(spaceIndex + 1);
  }
  return new URL(request.url).searchParams.get("token") ?? "";
}

// Matches the truthy strings pydantic's `bool` accepts for MCP_MULTI_TENANT
// (src/config.py) — "true"/"1"/"yes"/"on"/"y"/"t", case-insensitive — so an
// operator setting the secret to e.g. "True" or "1" (both valid there)
// doesn't silently keep every tenant on the single shared container here
// while the Python app itself is genuinely running in multi-tenant mode.
const TRUTHY = new Set(["true", "1", "yes", "on", "y", "t"]);
function isMultiTenant(env: Env): boolean {
  return TRUTHY.has((env.MCP_MULTI_TENANT ?? "").trim().toLowerCase());
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// A stable, non-reversible id for whichever container instance should serve
// this caller — never the raw token itself, so it doesn't sit around as a
// Durable Object name. Two requests with the same token always hash to the
// same id, so a tenant's traffic keeps landing on their own container.
async function tenantContainerId(request: Request): Promise<string | undefined> {
  const token = presentedToken(request);
  return token ? sha256Hex(token) : undefined;
}

// Rate-limit key: same per-caller hash as tenantContainerId (never the raw
// token — see above), so one caller's usage can't burn through another's
// quota. A missing/empty token collapses to one shared bucket for all
// unauthenticated traffic, which is fine — those requests get rejected by
// the Python app's own auth check regardless, this just caps how many of
// them can reach the container first.
async function rateLimitKey(request: Request): Promise<string> {
  return sha256Hex(presentedToken(request) || "anonymous");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/mcp" || pathname.startsWith("/mcp/")) {
      const { success } = await env.MCP_RATE_LIMITER.limit({ key: await rateLimitKey(request) });
      if (!success) {
        return new Response("Rate limit exceeded. Try again shortly.", { status: 429 });
      }

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
      const containerId = isMultiTenant(env) ? await tenantContainerId(request) : undefined;
      const container = getContainer(env.YNAB_MCP_CONTAINER, containerId);
      return container.fetch(request);
    }

    if (pathname === "/health") {
      // Always the shared/default instance — a liveness check isn't tied to
      // any one tenant.
      const container = getContainer(env.YNAB_MCP_CONTAINER);
      const response = await container.fetch(request);
      // Which Worker version actually answered — the question we had no
      // answer to while debugging the container naming conflict, where a
      // deploy could "succeed" on the Worker side while the container half
      // silently failed. This is the Worker's own version, not the
      // container image's — the two deploy together but aren't the same
      // artifact, so a mismatch between what you expect here and the image
      // tag in the Cloudflare dashboard's container logs is itself a signal.
      const headers = new Headers(response.headers);
      headers.set("X-Worker-Version-Id", env.CF_VERSION_METADATA.id);
      headers.set("X-Worker-Version-Tag", env.CF_VERSION_METADATA.tag || "untagged");
      return new Response(response.body, { status: response.status, headers });
    }

    // Everything else (/, /privacy-policy) is the static site built from
    // worker/site — Cloudflare serves it directly from the `assets` binding
    // in wrangler.jsonc before this fetch handler even runs, so a matching
    // request never reaches here. This only catches a genuinely unknown path.
    return new Response("Not found", { status: 404 });
  },
};
