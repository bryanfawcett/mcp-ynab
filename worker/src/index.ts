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
  // OAuth proxy (src/server/oauth.py) — all four optional; leaving any unset
  // keeps the deployment on the PAT-only flow. The Container reaches the
  // OAUTH_KV namespace over its REST API (a Container is separate compute
  // from the Worker, so it can't use the native `env.OAUTH_KV` binding
  // below), hence a scoped API token rather than the binding itself.
  YNAB_OAUTH_CLIENT_ID?: string;
  YNAB_OAUTH_CLIENT_SECRET?: string;
  CLOUDFLARE_ACCOUNT_ID?: string;
  CLOUDFLARE_KV_API_TOKEN?: string;
  MCP_RATE_LIMITER: RateLimit;
  CF_VERSION_METADATA: WorkerVersionMetadata;
}

// Not a secret (just an id, not a credential) and stable, so it's a literal
// here rather than a secret — must match wrangler.jsonc's kv_namespaces
// binding id. The Worker itself has no need to touch this KV namespace
// directly (only the Python container does, over the REST API above), so
// there's no `OAUTH_KV` binding used in this file despite one being declared
// in wrangler.jsonc.
const OAUTH_KV_NAMESPACE_ID = "afc28b10107f4fc591857970d92dc62c";

export class YnabMcpContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "10m";
  envVars = {
    YNAB_API_KEY: this.env.YNAB_API_KEY ?? "",
    MCP_AUTH_TOKEN: this.env.MCP_AUTH_TOKEN ?? "",
    MCP_MULTI_TENANT: this.env.MCP_MULTI_TENANT ?? "",
    YNAB_OAUTH_CLIENT_ID: this.env.YNAB_OAUTH_CLIENT_ID ?? "",
    YNAB_OAUTH_CLIENT_SECRET: this.env.YNAB_OAUTH_CLIENT_SECRET ?? "",
    CLOUDFLARE_ACCOUNT_ID: this.env.CLOUDFLARE_ACCOUNT_ID ?? "",
    CLOUDFLARE_KV_NAMESPACE_ID: OAUTH_KV_NAMESPACE_ID,
    CLOUDFLARE_KV_API_TOKEN: this.env.CLOUDFLARE_KV_API_TOKEN ?? "",
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

// @cloudflare/containers itself returns a bare 503 with an internal-sounding
// message ("There is no Container instance available... you have reached
// your max concurrent instance count...") when every one of max_instances
// (wrangler.jsonc) is already busy — i.e. too many concurrent users right
// now. Only that capacity path produces a 503 here (the Python app's own
// errors are MCP-protocol-level, not raw HTTP 503s), so replace it with a
// clear, branded response instead of leaking the library's wording.
function isAtCapacity(response: Response): boolean {
  return response.status === 503;
}

function capacityResponse(): Response {
  return new Response(
    JSON.stringify({
      error: "at_capacity",
      hint:
        "Nyuchi MCP for YNAB is at capacity for concurrent users right now. " +
        "Please try again in a minute or two — see https://ynab.nyuchi.com/project for status.",
    }),
    { status: 503, headers: { "content-type": "application/json", "Retry-After": "30" } },
  );
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
      const response = await container.fetch(request);
      return isAtCapacity(response) ? capacityResponse() : response;
    }

    if (pathname.startsWith("/oauth/") || pathname.startsWith("/.well-known/oauth-")) {
      // The OAuth proxy's own routes (src/server/oauth.py) — added there in
      // the same change that forgot to route them here, so every one of
      // these 404'd before ever reaching the container. Always the shared/
      // default instance: none of this is naturally per-tenant (a caller
      // has no token yet for most of this flow, and OAuth state lives in
      // KV, not in-process, so any container instance can serve it).
      const container = getContainer(env.YNAB_MCP_CONTAINER);
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
