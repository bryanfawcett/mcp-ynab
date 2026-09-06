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
      {
        title: "Real brand assets, wider layout",
        detail: "Fixed a sitewide dead-CSS bug, swapped a hand-drawn recreation for Nyuchi's actual bee logo, widened the cramped 760px content column, added the mineral-strip brand accent.",
        status: "done",
        ref: { type: "pr", number: 10 },
      },
      {
        title: "Config reliability: OAuth vars survive every deploy path",
        detail: "YNAB_OAUTH_CLIENT_ID/CLOUDFLARE_ACCOUNT_ID moved from versioned secrets (which kept silently vanishing across deploy paths) to source-controlled vars.",
        status: "done",
        ref: { type: "pr", number: 11 },
      },
      {
        title: "CI validates the Worker actually deploys",
        detail: "New worker-deploy-dryrun job replaces the equivalent Cloudflare Workers Builds check, which always failed on this repo's worker/-nested layout.",
        status: "done",
        ref: { type: "pr", number: 11 },
      },
      {
        title: "Astro security upgrade",
        detail: "worker/site is pinned to a vulnerable Astro 6.4.8; fix needs a breaking major-version bump to 7.3.1+.",
        status: "action",
        ref: { type: "issue", number: 12 },
      },
      {
        title: "Triage remaining Dependabot alerts",
        detail: "40 alerts flagged on main (19 high, 16 moderate, 5 low) -- some may overlap with the Astro bump above, but not all.",
        status: "action",
        ref: { type: "issue", number: 16 },
      },
      {
        title: "Clean up the stale Workers Builds check",
        detail: "Uncheck \"Builds for non-production branches\" in the Cloudflare dashboard now that CI covers the same thing properly.",
        status: "action",
        ref: { type: "issue", number: 14 },
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
        detail: "Sign in with YNAB directly, no personal access token to copy and paste. Confirmed live: /.well-known/oauth-authorization-server resolves correctly in production.",
        status: "done",
        ref: { type: "pr", number: 9 },
      },
      {
        title: "End-to-end test with a real YNAB login",
        detail: "The pieces (discovery, registration, authorize redirect) all check out programmatically, but nobody has walked the full sign-in flow through a real browser yet.",
        status: "action",
        ref: { type: "issue", number: 15 },
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
        title: "Status monitor",
        detail: "Open-source, Upptime-style /status page -- a scheduled GitHub Actions job checks the Worker, tools, YNAB API, and auth every 10 minutes.",
        status: "done",
        ref: { type: "pr", number: 11 },
      },
      {
        title: "Support portal",
        detail: "Intercom Messenger widget plus a published Help Center collection (6 articles) at support.nyuchi.com.",
        status: "done",
        ref: { type: "pr", number: 11 },
      },
      {
        title: "Support portal polish",
        detail: "Article ordering within the collection, and the table-of-contents/Copy-for-LLM Help Center display settings -- dashboard-only, not a code change.",
        status: "action",
        ref: { type: "issue", number: 13 },
      },
      {
        title: "Launch plan",
        detail: "Wider announcement now that OAuth, the support portal, and the status monitor are all live -- messaging, timing, and where to announce.",
        status: "action",
        ref: { type: "issue", number: 17 },
      },
    ],
  },
];
