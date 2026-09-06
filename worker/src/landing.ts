// Static landing page served at "/" — everything else (/mcp) goes to the
// Container instead (see index.ts). Kept as a plain string so serving it
// never wakes the container; this is meant to load instantly.
//
// Styling follows the Bundu brand system: colors and radii from the Mzizi
// design tokens (mzizi_get_tokens) — copper (#BF5A36 light / #FF8A65 dark)
// is Bundu's own ecosystem mineral, used here as the accent. Typography
// matches bryanfawcett.com's actual type system rather than Mzizi's generic
// Noto Sans/Serif defaults: Cormorant Garamond as the big display headline
// (that site's --display, used for its huge uppercase hero text), IBM Plex
// Serif for body copy, IBM Plex Mono for code — bryanfawcett.com has no
// sans-serif at all, it's an all-serif editorial identity.
export const LANDING_PAGE_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YNAB MCP Server</title>
<meta name="description" content="A personal Model Context Protocol server connecting AI assistants to a YNAB budget.">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23BF5A36'/%3E%3Ctext x='32' y='41' font-family='system-ui, sans-serif' font-weight='700' font-size='23' fill='%23FFFFFF' text-anchor='middle'%3E4C%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Serif:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    /* Bundu brand tokens — dark by default, overridden for light below.
       Type matches bryanfawcett.com: an all-serif system, no sans-serif. */
    --font-display: "Cormorant Garamond", ui-serif, Georgia, serif;
    --font-serif: "IBM Plex Serif", ui-serif, Georgia, serif;
    --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, monospace;

    --color-copper: #FF8A65;      /* Bundu ecosystem identity mineral (dark) */
    --bg-base: #0E0D0C;
    --bg-surface: #131211;
    --bg-raised: #2E2C29;
    --border: #2A2927;            /* warm stone, not cool gray */
    --text-primary: #F3F3F1;
    --text-secondary: #A09C93;    /* semantic "neutral" token */

    --radius-lg: 14px;            /* card radius per componentSpecs */
    --radius-full: 9999px;        /* buttons/badges are always pill-shaped */
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme]) {
      --color-copper: #BF5A36;
      --bg-base: #F3F3F1;
      --bg-surface: #EEEEEC;
      --bg-raised: #D6D5D1;
      --border: #E7E5E0;
      --text-primary: #1A1918;
      --text-secondary: #55514B;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg-base);
    color: var(--text-primary);
    font: 16px/1.6 var(--font-serif);
  }
  main { max-width: 760px; margin: 0 auto; padding: 4rem 1.5rem 5rem; }
  .badge {
    display: inline-flex; align-items: center; gap: .5rem;
    padding: .3rem .75rem; border: 1px solid var(--border); border-radius: var(--radius-full);
    font-size: .75rem; color: var(--text-secondary); margin-bottom: 2rem;
  }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-copper); }
  h1 {
    font-family: var(--font-display); font-weight: 700;
    text-transform: uppercase; letter-spacing: .01em;
    font-size: clamp(2.75rem, 4vw + 1.5rem, 5.5rem);
    line-height: .95; margin: 0 0 1rem;
  }
  h1 span { color: var(--color-copper); }
  p.lede { color: var(--text-secondary); font-size: 1.125rem; max-width: 60ch; margin: 0 0 2.5rem; }
  h2 { font-family: var(--font-serif); font-weight: 600; font-size: 1.5rem; margin: 3rem 0 1rem; }
  .card {
    background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
    padding: 1.5rem;
  }
  code, .mono { font: 0.9em/1.5 var(--font-mono); }
  .endpoint {
    display: flex; align-items: center; gap: .75rem; flex-wrap: wrap;
    background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
    padding: 1rem 1.25rem; margin-bottom: 2.5rem;
  }
  .endpoint code { color: var(--color-copper); font-size: .95rem; }
  ul.features { list-style: none; margin: 0; padding: 0; display: grid; gap: .9rem; }
  ul.features li { padding-left: 1.4rem; position: relative; }
  ul.features li::before { content: "→"; position: absolute; left: 0; color: var(--color-copper); }
  ul.features b { color: var(--text-primary); }
  table { width: 100%; border-collapse: collapse; font-size: .88rem; }
  th, td { text-align: left; padding: .6rem .75rem; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--text-secondary); font-weight: 500; width: 9rem; }
  td code { color: var(--color-copper); }
  a { color: var(--color-copper); text-decoration: none; }
  a:hover { text-decoration: underline; }
  footer { margin-top: 4rem; padding-top: 2rem; border-top: 1px solid var(--border); color: var(--text-secondary); font-size: .85rem; }
  footer a { color: var(--text-secondary); }
</style>
</head>
<body>
<main>
  <div class="badge"><span class="dot"></span> Running on Cloudflare — always on, no local install</div>
  <h1>Talk to your budget<br><span>in plain English.</span></h1>
  <p class="lede">
    A remote deployment of <a href="https://github.com/bryanfawcett/mcp-ynab" target="_blank" rel="noopener">mcp-ynab</a>,
    an open-source <a href="https://modelcontextprotocol.io" target="_blank" rel="noopener">Model Context Protocol</a>
    server that connects an AI assistant directly to a <a href="https://www.ynab.com/" target="_blank" rel="noopener">YNAB</a>
    budget. The upstream project runs locally, one process per machine; this instance runs as a
    Cloudflare Container behind this Worker, so any MCP client that speaks remote connectors — Claude
    and ChatGPT included — can reach it without installing anything first.
  </p>

  <div class="endpoint">
    <span class="mono" style="color:var(--text-secondary)">MCP endpoint —</span>
    <code>https://budget.bryanfawcett.com/mcp</code>
  </div>

  <h2>What it does</h2>
  <div class="card">
    <ul class="features">
      <li><b>50+ tools</b> — budgets, accounts, transactions, categories, payees, months, scheduled transactions, analytics, and reconciliation</li>
      <li><b>Delta sync</b> — only fetches what changed since the last call, using YNAB's server knowledge</li>
      <li><b>4-tier caching</b> — TTL cache, delta sync, retry with backoff, persistent storage</li>
      <li><b>Search &amp; analytics</b> — text search across transactions, per-category spending breakdowns, money-flow data</li>
      <li><b>Monthly reports with a live dashboard</b> — income/spending summary, category and payee breakdowns, overspent categories, and a multi-month trend, rendered as an interactive dashboard on MCP Apps-capable hosts (Claude, ChatGPT)</li>
      <li><b>Bulk operations</b> — create or update multiple transactions in a single call</li>
      <li><b>Dollar amounts</b> — accepts plain dollars, converts to YNAB's internal format automatically</li>
    </ul>
  </div>

  <h2>Available tools</h2>
  <div class="card">
    <table>
      <tbody>
        <tr><th>User</th><td><code>get_user</code></td></tr>
        <tr><th>Plans</th><td><code>list_plans</code>, <code>get_plan</code>, <code>get_plan_settings</code></td></tr>
        <tr><th>Accounts</th><td><code>list_accounts</code>, <code>get_account</code>, <code>create_account</code></td></tr>
        <tr><th>Categories</th><td><code>list_categories</code>, <code>get_category</code>, <code>create_category</code>, <code>update_category</code>, <code>create_category_group</code>, <code>update_category_group</code>, <code>get_category_for_month</code>, <code>update_category_for_month</code></td></tr>
        <tr><th>Payees</th><td><code>list_payees</code>, <code>create_payee</code>, <code>get_payee</code>, <code>update_payee</code></td></tr>
        <tr><th>Payee locations</th><td><code>list_payee_locations</code>, <code>get_payee_location</code>, <code>get_payee_locations_by_payee</code></td></tr>
        <tr><th>Months</th><td><code>list_months</code>, <code>get_month</code></td></tr>
        <tr><th>Money movements</th><td><code>list_money_movements</code>, <code>get_money_movements_for_month</code>, <code>list_money_movement_groups</code>, <code>get_money_movement_groups_for_month</code></td></tr>
        <tr><th>Transactions</th><td><code>list_transactions</code>, <code>get_transaction</code>, <code>get_transactions_by_account</code>, <code>get_transactions_by_category</code>, <code>get_transactions_by_month</code>, <code>get_transactions_by_payee</code>, <code>search_transactions</code>, <code>create_transaction</code>, <code>create_transactions</code>, <code>update_transaction</code>, <code>update_transactions</code>, <code>delete_transaction</code>, <code>import_transactions</code></td></tr>
        <tr><th>Scheduled</th><td><code>list_scheduled_transactions</code>, <code>get_scheduled_transaction</code>, <code>create_scheduled_transaction</code>, <code>update_scheduled_transaction</code>, <code>delete_scheduled_transaction</code></td></tr>
        <tr><th>Analytics</th><td><code>get_money_flow</code>, <code>get_spending_by_category</code>, <code>get_monthly_report</code></td></tr>
        <tr><th>Reconciliation</th><td><code>export_transactions_csv</code>, <code>reconcile_account</code></td></tr>
      </tbody>
    </table>
  </div>

  <h2>Connecting</h2>
  <div class="card">
    <p style="margin:0 0 1rem;">
      Every request needs a bearer token — and here, that token is your own
      <a href="https://app.ynab.com/settings/developer" target="_blank" rel="noopener">YNAB personal access token</a>,
      not a password for this site. It's used only to make YNAB API calls on your behalf, for
      that request; nobody else's budget is visible to you and yours isn't visible to them.
    </p>
    <p style="margin:0 0 1rem;">
      In Claude web (<b>Settings → Connectors → Add custom connector</b>), use the
      MCP endpoint above with <code>?token=&lt;your-YNAB-token&gt;</code> appended; clients that
      support custom headers can send <code>Authorization: Bearer &lt;your-YNAB-token&gt;</code>
      instead.
    </p>
    <p style="margin:0;">
      Running the open-source server yourself instead — for just you, or for others under
      your own domain? See
      <a href="https://github.com/bryanfawcett/mcp-ynab" target="_blank" rel="noopener">this fork</a>'s
      README for the Cloudflare deployment, or
      <a href="https://mcp-ynab.com" target="_blank" rel="noopener">mcp-ynab.com</a> for the local
      stdio setup (Claude Desktop, Claude Code, ChatGPT).
    </p>
  </div>

  <footer>
    Runs the open-source <a href="https://github.com/bryanfawcett/mcp-ynab" target="_blank" rel="noopener">mcp-ynab</a>
    server on a Cloudflare Container. AGPL-3.0 licensed.
  </footer>
</main>
</body>
</html>
`;
