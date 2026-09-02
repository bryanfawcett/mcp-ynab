// Static landing page served at "/" — everything else (/mcp) goes to the
// Container instead (see index.ts). Kept as a plain string so serving it
// never wakes the container; this is meant to load instantly.
export const LANDING_PAGE_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YNAB MCP Server</title>
<meta name="description" content="A personal Model Context Protocol server connecting AI assistants to a YNAB budget.">
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #0a0a0a;
    color: #e5e5e5;
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  main { max-width: 760px; margin: 0 auto; padding: 4rem 1.5rem 5rem; }
  .badge {
    display: inline-flex; align-items: center; gap: .5rem;
    padding: .3rem .75rem; border: 1px solid rgba(255,255,255,.1); border-radius: 999px;
    font-size: .75rem; color: #9ca3af; margin-bottom: 2rem;
  }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; background: #22d3ee; }
  h1 { font-size: 2.5rem; line-height: 1.15; margin: 0 0 1rem; letter-spacing: -0.02em; }
  h1 span { color: #22d3ee; }
  p.lede { color: #9ca3af; font-size: 1.05rem; max-width: 60ch; margin: 0 0 2.5rem; }
  h2 { font-size: 1.35rem; margin: 3rem 0 1rem; }
  .card {
    background: #141414; border: 1px solid rgba(255,255,255,.06); border-radius: 12px;
    padding: 1.5rem;
  }
  code, .mono { font: 0.9em/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .endpoint {
    display: flex; align-items: center; gap: .75rem; flex-wrap: wrap;
    background: #141414; border: 1px solid rgba(255,255,255,.06); border-radius: 10px;
    padding: 1rem 1.25rem; margin-bottom: 2.5rem;
  }
  .endpoint code { color: #22d3ee; font-size: .95rem; }
  ul.features { list-style: none; margin: 0; padding: 0; display: grid; gap: .9rem; }
  ul.features li { padding-left: 1.4rem; position: relative; color: #d4d4d4; }
  ul.features li::before { content: "→"; position: absolute; left: 0; color: #22d3ee; }
  ul.features b { color: #f5f5f5; }
  table { width: 100%; border-collapse: collapse; font-size: .88rem; }
  th, td { text-align: left; padding: .6rem .75rem; border-bottom: 1px solid rgba(255,255,255,.06); vertical-align: top; }
  th { color: #9ca3af; font-weight: 500; width: 9rem; }
  td { color: #c4c4c4; }
  td code { color: #a5f3fc; }
  a { color: #22d3ee; text-decoration: none; }
  a:hover { text-decoration: underline; }
  footer { margin-top: 4rem; padding-top: 2rem; border-top: 1px solid rgba(255,255,255,.06); color: #737373; font-size: .85rem; }
  footer a { color: #a3a3a3; }
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
    web included — can reach it without installing anything first.
  </p>

  <div class="endpoint">
    <span class="mono" style="color:#9ca3af">MCP endpoint —</span>
    <code>https://budget.bryanfawcett.com/mcp</code>
  </div>

  <h2>What it does</h2>
  <div class="card">
    <ul class="features">
      <li><b>30+ tools</b> — budgets, accounts, transactions, categories, payees, months, scheduled transactions, and analytics</li>
      <li><b>Delta sync</b> — only fetches what changed since the last call, using YNAB's server knowledge</li>
      <li><b>4-tier caching</b> — TTL cache, delta sync, retry with backoff, persistent storage</li>
      <li><b>Search &amp; analytics</b> — text search across transactions, per-category spending breakdowns, money-flow data</li>
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
        <tr><th>Payees</th><td><code>list_payees</code>, <code>get_payee</code>, <code>update_payee</code></td></tr>
        <tr><th>Payee locations</th><td><code>list_payee_locations</code>, <code>get_payee_location</code>, <code>get_payee_locations_by_payee</code></td></tr>
        <tr><th>Months</th><td><code>list_months</code>, <code>get_month</code></td></tr>
        <tr><th>Money movements</th><td><code>list_money_movements</code>, <code>get_money_movements_for_month</code>, <code>list_money_movement_groups</code>, <code>get_money_movement_groups_for_month</code></td></tr>
        <tr><th>Transactions</th><td><code>list_transactions</code>, <code>get_transaction</code>, <code>get_transactions_by_account</code>, <code>get_transactions_by_category</code>, <code>get_transactions_by_month</code>, <code>get_transactions_by_payee</code>, <code>search_transactions</code>, <code>create_transaction</code>, <code>create_transactions</code>, <code>update_transaction</code>, <code>update_transactions</code>, <code>delete_transaction</code>, <code>import_transactions</code></td></tr>
        <tr><th>Scheduled</th><td><code>list_scheduled_transactions</code>, <code>get_scheduled_transaction</code>, <code>create_scheduled_transaction</code>, <code>update_scheduled_transaction</code>, <code>delete_scheduled_transaction</code></td></tr>
        <tr><th>Analytics</th><td><code>get_money_flow</code>, <code>get_spending_by_category</code></td></tr>
      </tbody>
    </table>
  </div>

  <h2>Connecting</h2>
  <div class="card">
    <p style="margin:0 0 1rem;color:#d4d4d4;">
      This is a private, single-user instance — every request needs a bearer token.
      In Claude web (<b>Settings → Connectors → Add custom connector</b>), use the
      MCP endpoint above with <code>?token=&lt;token&gt;</code> appended; clients that support
      custom headers can send <code>Authorization: Bearer &lt;token&gt;</code> instead.
    </p>
    <p style="margin:0;color:#d4d4d4;">
      Running the open-source server yourself instead? See
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
