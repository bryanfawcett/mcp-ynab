"""MCP Apps UI resource for get_monthly_report.

Implements the MCP Apps extension (SEP-1865, https://github.com/modelcontextprotocol/ext-apps):
a `ui://` resource containing an HTML app, linked to a tool via that tool's
`meta={"ui": {"resourceUri": ...}}`. Hosts that support MCP Apps (Claude web/Desktop,
as of early 2026) render the resource in a sandboxed iframe after the linked tool
is called, and the app reads the tool's result via the `@modelcontextprotocol/ext-apps`
JS library's `ontoolresult` handler.

This app reads `result.content[0].text` (the same JSON string every tool in this
server already returns) rather than `result.structuredContent`, so get_monthly_report
needed no changes: giving it a Pydantic/TypedDict return type instead of `str` to get
SDK-native structuredContent would break handle_errors, whose error branches return a
plain JSON string incompatible with a structured-output schema.
"""

from src.server import _shared

DASHBOARD_URI = "ui://mcp-ynab/dashboard.html"

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<title>Budget Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
<script type="importmap">
{
  "imports": {
    "@modelcontextprotocol/ext-apps": "https://esm.sh/@modelcontextprotocol/ext-apps@1.7.5?deps=zod@4.1.13"
  }
}
</script>
<style>
  :root {
    --font-sans: system-ui, -apple-system, "Segoe UI", sans-serif;
    --color-bg: #0a0a0a;
    --color-card: #141414;
    --color-border: rgba(255,255,255,.08);
    --color-text-primary: #e5e5e5;
    --color-text-secondary: #9ca3af;
    --color-accent: #22d3ee;
    --color-negative: #f87171;
    --color-positive: #4ade80;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme]) {
      --color-bg: #ffffff;
      --color-card: #f7f7f8;
      --color-border: rgba(0,0,0,.08);
      --color-text-primary: #18181b;
      --color-text-secondary: #52525b;
    }
  }
  [data-theme="light"] {
    --color-bg: #ffffff;
    --color-card: #f7f7f8;
    --color-border: rgba(0,0,0,.08);
    --color-text-primary: #18181b;
    --color-text-secondary: #52525b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: var(--font-sans);
    background: var(--color-bg);
    color: var(--color-text-primary);
    padding: 16px;
  }
  h1 { font-size: 1.15rem; margin: 0 0 2px; }
  .subtitle { color: var(--color-text-secondary); font-size: .85rem; margin: 0 0 16px; }
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px;
    margin-bottom: 16px;
  }
  .card {
    background: var(--color-card);
    border: 1px solid var(--color-border);
    border-radius: 10px;
    padding: 12px 14px;
  }
  .kpi-label { font-size: .72rem; color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .03em; }
  .kpi-value { font-size: 1.25rem; font-weight: 600; margin-top: 2px; }
  .kpi-value.negative { color: var(--color-negative); }
  .kpi-value.positive { color: var(--color-positive); }
  .chart-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
  }
  @media (max-width: 640px) {
    .chart-row { grid-template-columns: 1fr; }
  }
  .chart-card { height: 240px; }
  .chart-card h2, .table-card h2 { font-size: .85rem; margin: 0 0 8px; color: var(--color-text-secondary); font-weight: 600; }
  .chart-card .chart-wrap { position: relative; height: 190px; }
  .table-card { margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: .82rem; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--color-border); }
  th { color: var(--color-text-secondary); font-weight: 500; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .table-row-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  @media (max-width: 640px) {
    .table-row-pair { grid-template-columns: 1fr; }
  }
  .empty { color: var(--color-text-secondary); font-size: .82rem; padding: 8px 0; }
  #status { color: var(--color-text-secondary); font-size: .85rem; }
  #error { color: var(--color-negative); font-size: .85rem; }
</style>
</head>
<body>
  <div id="app">
    <p id="status">Waiting for report data&hellip;</p>
  </div>

<script type="module">
import { App, applyDocumentTheme, applyHostStyleVariables, applyHostFonts } from "@modelcontextprotocol/ext-apps";

const appEl = document.getElementById("app");
const fmtUSD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const fmtMonth = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });

const PALETTE = ["#22d3ee", "#a78bfa", "#f472b6", "#4ade80", "#fbbf24", "#60a5fa", "#f87171", "#34d399"];
let charts = [];

function destroyCharts() {
  for (const c of charts) c.destroy();
  charts = [];
}

function handleHostContextChanged(ctx) {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
}

function showError(message) {
  destroyCharts();
  appEl.innerHTML = `<p id="error">Couldn't load the report: ${escapeHtml(message)}</p>`;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = String(s);
  return div.innerHTML;
}

function render(data) {
  destroyCharts();

  const s = data.summary || {};
  const netClass = s.net > 0 ? "positive" : s.net < 0 ? "negative" : "";
  const overspentClass = s.overspent_category_count > 0 ? "negative" : "";

  appEl.innerHTML = `
    <h1>Budget Dashboard</h1>
    <p class="subtitle">${escapeHtml(fmtMonth(data.month))}</p>

    <div class="kpi-row">
      <div class="card"><div class="kpi-label">Income</div><div class="kpi-value">${fmtUSD.format(s.income ?? 0)}</div></div>
      <div class="card"><div class="kpi-label">Spent</div><div class="kpi-value">${fmtUSD.format(s.spent ?? 0)}</div></div>
      <div class="card"><div class="kpi-label">Net</div><div class="kpi-value ${netClass}">${fmtUSD.format(s.net ?? 0)}</div></div>
      <div class="card"><div class="kpi-label">Savings Rate</div><div class="kpi-value">${s.savings_rate_pct == null ? "&mdash;" : s.savings_rate_pct + "%"}</div></div>
      <div class="card"><div class="kpi-label">Age of Money</div><div class="kpi-value">${s.age_of_money ?? "&mdash;"}</div></div>
      <div class="card"><div class="kpi-label">Overspent</div><div class="kpi-value ${overspentClass}">${s.overspent_category_count ?? 0} ${s.overspent_total ? "(" + fmtUSD.format(s.overspent_total) + ")" : ""}</div></div>
    </div>

    <div class="chart-row">
      <div class="card chart-card">
        <h2>Spending by Category Group</h2>
        <div class="chart-wrap"><canvas id="groupsChart"></canvas></div>
      </div>
      <div class="card chart-card">
        <h2>Top Categories: Budgeted vs Spent</h2>
        <div class="chart-wrap"><canvas id="categoriesChart"></canvas></div>
      </div>
    </div>

    <div class="card chart-card" style="height: 260px; margin-bottom: 12px;">
      <h2>Trend</h2>
      <div class="chart-wrap"><canvas id="trendChart"></canvas></div>
    </div>

    <div class="table-row-pair">
      <div class="card table-card">
        <h2>Overspent Categories</h2>
        ${renderOverspentTable(data.overspent_categories || [])}
      </div>
      <div class="card table-card">
        <h2>Top Payees</h2>
        ${renderPayeesTable(data.top_payees || [])}
      </div>
    </div>
  `;

  const textColor = getComputedStyle(document.body).getPropertyValue("--color-text-secondary").trim() || "#9ca3af";
  const gridColor = getComputedStyle(document.body).getPropertyValue("--color-border").trim() || "rgba(255,255,255,.08)";
  Chart.defaults.color = textColor;
  Chart.defaults.borderColor = gridColor;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

  const groups = data.category_groups || [];
  charts.push(new Chart(document.getElementById("groupsChart"), {
    type: "doughnut",
    data: {
      labels: groups.map((g) => g.name),
      datasets: [{ data: groups.map((g) => g.spent), backgroundColor: PALETTE, borderWidth: 0 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } },
    },
  }));

  const cats = data.top_categories || [];
  charts.push(new Chart(document.getElementById("categoriesChart"), {
    type: "bar",
    data: {
      labels: cats.map((c) => c.name),
      datasets: [
        { label: "Budgeted", data: cats.map((c) => c.budgeted), backgroundColor: "#60a5fa88" },
        { label: "Spent", data: cats.map((c) => c.spent), backgroundColor: PALETTE[0] },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { x: { ticks: { font: { size: 9 } } }, y: { beginAtZero: true } },
      plugins: { legend: { position: "top", labels: { boxWidth: 10, font: { size: 10 } } } },
    },
  }));

  const trend = data.trend || [];
  charts.push(new Chart(document.getElementById("trendChart"), {
    type: "line",
    data: {
      labels: trend.map((t) => fmtMonth(t.month)),
      datasets: [
        { label: "Income", data: trend.map((t) => t.income), borderColor: PALETTE[3], backgroundColor: "transparent", tension: .3 },
        { label: "Spent", data: trend.map((t) => t.spent), borderColor: PALETTE[6], backgroundColor: "transparent", tension: .3 },
        { label: "Net", data: trend.map((t) => t.net), borderColor: PALETTE[0], backgroundColor: "transparent", tension: .3, borderDash: [4, 3] },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "top", labels: { boxWidth: 10, font: { size: 10 } } } },
    },
  }));
}

function renderOverspentTable(rows) {
  if (!rows.length) return `<p class="empty">Nothing overspent this month.</p>`;
  const body = rows.map((r) => `
    <tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.group)}</td><td class="num">${fmtUSD.format(r.overspent_by)}</td></tr>
  `).join("");
  return `<table><thead><tr><th>Category</th><th>Group</th><th>Over by</th></tr></thead><tbody>${body}</tbody></table>`;
}

function renderPayeesTable(rows) {
  if (!rows.length) return `<p class="empty">No payee spending this month.</p>`;
  const body = rows.map((r) => `
    <tr><td>${escapeHtml(r.name)}</td><td class="num">${r.transaction_count}</td><td class="num">${fmtUSD.format(r.spent)}</td></tr>
  `).join("");
  return `<table><thead><tr><th>Payee</th><th># Txns</th><th>Spent</th></tr></thead><tbody>${body}</tbody></table>`;
}

const app = new App({ name: "Budget Dashboard", version: "1.0.0" });

app.onteardown = async () => {
  destroyCharts();
  return {};
};

app.ontoolinput = () => {
  appEl.innerHTML = `<p id="status">Loading report&hellip;</p>`;
};

app.ontoolresult = (result) => {
  try {
    const text = result?.content?.[0]?.text;
    if (!text) { showError("empty tool result"); return; }
    const data = JSON.parse(text);
    if (result.isError || data?.error) { showError(data?.error || "unknown error"); return; }
    render(data);
  } catch (e) {
    showError(e?.message || String(e));
  }
};

app.ontoolcancelled = () => {
  appEl.innerHTML = `<p id="status">Cancelled.</p>`;
};

app.onerror = (e) => showError(e?.message || String(e));

app.onhostcontextchanged = handleHostContextChanged;

app.connect().then(() => {
  const ctx = app.getHostContext();
  if (ctx) handleHostContextChanged(ctx);
});
</script>
</body>
</html>
"""


@_shared.mcp.resource(
    DASHBOARD_URI,
    mime_type="text/html;profile=mcp-app",
    meta={"ui": {"csp": {"resourceDomains": ["https://esm.sh", "https://cdn.jsdelivr.net"]}}},
)
def dashboard_view() -> str:
    """Budget dashboard UI resource, rendered from get_monthly_report's output."""
    return DASHBOARD_HTML
