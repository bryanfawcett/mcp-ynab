import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  YNAB_MCP_CONTAINER: DurableObjectNamespace<YnabMcpContainer>;
  // Set both with `wrangler secret put`, not in wrangler.jsonc — see README.md.
  YNAB_API_KEY: string;
  MCP_AUTH_TOKEN: string;
}

export class YnabMcpContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "10m";
  envVars = {
    YNAB_API_KEY: this.env.YNAB_API_KEY,
    MCP_AUTH_TOKEN: this.env.MCP_AUTH_TOKEN,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // One person's YNAB budget, not a multi-tenant service — every request
    // is routed to the same container instance.
    const container = getContainer(env.YNAB_MCP_CONTAINER);
    return container.fetch(request);
  },
};
