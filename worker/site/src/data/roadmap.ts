// Public project-dashboard data for /project. Plain data, not a live store:
// this site is served publicly with no auth, so making it directly editable
// here (the way the internal Claude-hosted project dashboard is) would let
// any visitor deface it. Update this file and redeploy instead -- it's the
// same review path as any other change to the site.
export type TaskStatus = "done" | "action" | "blocked";

export const REPO = "bryanfawcett/mcp-ynab";

export interface TaskRef {
  type: "pr" | "issue";
  number: number;
}

export interface RoadmapTask {
  title: string;
  detail: string;
  status: TaskStatus;
  ref?: TaskRef;
}

export interface RoadmapCategory {
  name: string;
  tasks: RoadmapTask[];
}

export const ROADMAP: RoadmapCategory[] = [
  {
    name: "Infrastructure",
    tasks: [
      {
        title: "Multi-tenant mode",
        detail: "Each caller brings their own YNAB token, resolved to a fully isolated client, cache, and delta-sync state.",
        status: "done",
        ref: { type: "pr", number: 5 },
      },
      {
        title: "Per-tenant container routing",
        detail: "Each tenant's token routes to its own container instance, not just its own process -- independent CPU, memory, and idle timer.",
        status: "done",
        ref: { type: "pr", number: 6 },
      },
      {
        title: "Cross-tenant session hijack fix",
        detail: "Stateless HTTP transport, so a leaked session id can never be reused to execute requests under a different tenant's credentials.",
        status: "done",
        ref: { type: "pr", number: 7 },
      },
      {
        title: "Observability",
        detail: "Request logs and traces enabled, plus a way to confirm which deployed version is actually live.",
        status: "done",
        ref: { type: "pr", number: 7 },
      },
      {
        title: "Per-caller rate limiting",
        detail: "100 requests/60s per caller on /mcp, so one client can't burn through another's quota.",
        status: "done",
        ref: { type: "pr", number: 8 },
      },
      {
        title: "Scale headroom for concurrent users",
        detail: "Container capacity raised well past the OAuth app's current Restricted Mode cap.",
        status: "done",
        ref: { type: "pr", number: 8 },
      },
    ],
  },
  {
    name: "OAuth Proxy",
    tasks: [
      {
        title: "YNAB OAuth application registered",
        detail: "Name, description, URLs, privacy policy, and redirect URI all set up directly with YNAB.",
        status: "done",
      },
      {
        title: "Durable storage for tokens",
        detail: "A dedicated store for authorization codes, refresh tokens, and registered clients -- the container's own disk is wiped on every idle-sleep, so this can't live there.",
        status: "done",
        ref: { type: "pr", number: 8 },
      },
      {
        title: "OAuth proxy server",
        detail: "Sign in with YNAB directly, no personal access token to copy and paste. In development.",
        status: "blocked",
      },
    ],
  },
  {
    name: "Launch",
    tasks: [
      {
        title: "Privacy policy",
        detail: "Published, with a working data-deletion contact.",
        status: "done",
        ref: { type: "pr", number: 7 },
      },
      {
        title: "Public project dashboard",
        detail: "This page.",
        status: "done",
        ref: { type: "pr", number: 8 },
      },
      {
        title: "Launch plan",
        detail: "Wider announcement once the OAuth proxy is live, so new users get the one-click sign-in flow from day one instead of the personal-access-token workaround.",
        status: "action",
      },
    ],
  },
];
