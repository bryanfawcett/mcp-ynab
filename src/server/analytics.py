import asyncio
import json
from datetime import date

from src.models.common import milliunits_to_dollars
from src.server import _shared, icons
from src.server.dashboard import DASHBOARD_URI  # also registers the dashboard ui:// resource

MONEY_FLOW_EXCLUDE_GROUPS = {"Internal Master Category", "Credit Card Payments"}


@_shared.mcp.tool(icons=[icons.ANALYTICS])
@_shared.handle_errors
async def get_money_flow(plan_id: str, month: str = "current") -> str:
    """Build Sankey chart data showing money flow from income sources to spending category groups.

    Returns nodes and index-based links suitable for Sankey/flow visualizations.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        month: Month in YYYY-MM-DD format (first of month, e.g. '2026-03-01') or 'current'
    """
    if month == "current":
        today = date.today()
        month = today.replace(day=1).strftime("%Y-%m-%d")

    # Fetch month detail (has categories with activity and income total)
    month_detail = await _shared.cache.get_month(month, plan_id)

    # Group categories by category_group_name and sum activity
    group_activity: dict[str, int] = {}
    for cat in month_detail.categories:
        group_name = cat.category_group_name or "Uncategorized"
        if group_name in MONEY_FLOW_EXCLUDE_GROUPS:
            continue
        group_activity[group_name] = group_activity.get(group_name, 0) + cat.activity

    # Filter out groups with zero activity
    group_activity = {name: activity for name, activity in group_activity.items() if activity != 0}

    # Build nodes: index 0 is Income, then one per category group
    nodes = [{"name": "Income"}]
    links = []
    total_spent_mu = 0

    for group_name, activity_mu in sorted(group_activity.items()):
        abs_mu = abs(activity_mu)
        total_spent_mu += abs_mu
        target_index = len(nodes)
        nodes.append({"name": group_name})
        links.append({"source": 0, "target": target_index, "value": milliunits_to_dollars(abs_mu)})

    result = {
        "month": month,
        "total_income": milliunits_to_dollars(abs(month_detail.income)),
        "total_spent": milliunits_to_dollars(total_spent_mu),
        "nodes": nodes,
        "links": links,
    }
    return json.dumps(result, indent=2)


@_shared.mcp.tool(icons=[icons.ANALYTICS])
@_shared.handle_errors
async def get_spending_by_category(plan_id: str, month: str = "current") -> str:
    """Get per-category spending breakdown for a month, with budget vs actual comparison.

    Returns categories sorted by spending (highest first), grouped by category group,
    with budgeted, spent, balance, and percentage of total spending.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        month: Month in YYYY-MM-DD format (first of month, e.g. '2026-03-01') or 'current'
    """
    if month == "current":
        today = date.today()
        month = today.replace(day=1).strftime("%Y-%m-%d")

    month_detail = await _shared.cache.get_month(month, plan_id)

    # Collect categories with non-zero activity, excluding internal groups
    categories = []
    total_spent_mu = 0
    for cat in month_detail.categories:
        group_name = cat.category_group_name or "Uncategorized"
        if group_name in MONEY_FLOW_EXCLUDE_GROUPS:
            continue
        if cat.activity == 0:
            continue
        spent_mu = abs(cat.activity)
        total_spent_mu += spent_mu
        categories.append({
            "group": group_name,
            "name": cat.name,
            "budgeted_mu": cat.budgeted,
            "spent_mu": spent_mu,
            "balance_mu": cat.balance,
        })

    # Sort by spending (highest first) and compute percentages
    categories.sort(key=lambda c: c["spent_mu"], reverse=True)
    result_cats = []
    for c in categories:
        pct = round(c["spent_mu"] / total_spent_mu * 100, 1) if total_spent_mu > 0 else 0.0
        result_cats.append({
            "group": c["group"],
            "name": c["name"],
            "budgeted": milliunits_to_dollars(c["budgeted_mu"]),
            "spent": milliunits_to_dollars(c["spent_mu"]),
            "balance": milliunits_to_dollars(c["balance_mu"]),
            "pct_of_total": pct,
        })

    result = {
        "month": month,
        "total_spent": milliunits_to_dollars(total_spent_mu),
        "categories": result_cats,
    }
    return json.dumps(result, indent=2)


@_shared.mcp.tool(
    icons=[icons.ANALYTICS],
    meta={"ui": {"resourceUri": DASHBOARD_URI}, "ui/resourceUri": DASHBOARD_URI},
)
@_shared.handle_errors
async def get_monthly_report(
    plan_id: str, month: str = "current", trend_months: int = 6, top_n: int = 8
) -> str:
    """Build a full monthly budget report: income/spending summary, category-group and
    top-category breakdowns, overspent categories, top payees, and a multi-month trend.

    On hosts that support MCP Apps (e.g. Claude, ChatGPT), this renders as an
    interactive dashboard (KPI tiles, charts, tables) automatically — no separate
    artifact needed. On hosts that don't, the same data comes back as JSON. Ask for
    this instead of combining get_spending_by_category and get_money_flow separately.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        month: Month in YYYY-MM-DD format (first of month, e.g. '2026-03-01') or 'current'
        trend_months: Number of months of history to include in the trend, ending at
            `month` (default 6)
        top_n: How many top categories and top payees to include (default 8)
    """
    if month == "current":
        today = date.today()
        month = today.replace(day=1).strftime("%Y-%m-%d")

    month_detail, transactions, all_months = await asyncio.gather(
        _shared.cache.get_month(month, plan_id),
        _shared.cache.get_transactions_by_month(month, plan_id),
        _shared.cache.get_months(plan_id),
    )

    budget_categories = [
        c for c in month_detail.categories
        if (c.category_group_name or "Uncategorized") not in MONEY_FLOW_EXCLUDE_GROUPS
    ]

    income_mu = abs(month_detail.income)
    spent_mu = sum(abs(c.activity) for c in budget_categories)
    net_mu = income_mu - spent_mu
    savings_rate = round(net_mu / income_mu * 100, 1) if income_mu > 0 else None

    # Category groups, for a bar chart or treemap.
    group_totals: dict[str, dict[str, int]] = {}
    for c in budget_categories:
        group = group_totals.setdefault(
            c.category_group_name or "Uncategorized",
            {"budgeted_mu": 0, "spent_mu": 0, "balance_mu": 0},
        )
        group["budgeted_mu"] += c.budgeted
        group["spent_mu"] += abs(c.activity)
        group["balance_mu"] += c.balance

    category_groups = [
        {
            "name": name,
            "budgeted": milliunits_to_dollars(v["budgeted_mu"]),
            "spent": milliunits_to_dollars(v["spent_mu"]),
            "balance": milliunits_to_dollars(v["balance_mu"]),
        }
        for name, v in sorted(group_totals.items(), key=lambda kv: kv[1]["spent_mu"], reverse=True)
    ]

    # Top individual categories by spend.
    spending_cats = sorted(
        (c for c in budget_categories if c.activity != 0),
        key=lambda c: abs(c.activity),
        reverse=True,
    )
    top_categories = [
        {
            "name": c.name,
            "group": c.category_group_name or "Uncategorized",
            "budgeted": milliunits_to_dollars(c.budgeted),
            "spent": milliunits_to_dollars(abs(c.activity)),
            "balance": milliunits_to_dollars(c.balance),
        }
        for c in spending_cats[:top_n]
    ]

    # Categories currently over budget (negative balance carries into next month as debt).
    overspent = sorted(
        (
            {
                "name": c.name,
                "group": c.category_group_name or "Uncategorized",
                "overspent_by": milliunits_to_dollars(abs(c.balance)),
            }
            for c in budget_categories
            if c.balance < 0
        ),
        key=lambda o: o["overspent_by"],
        reverse=True,
    )

    # Top payees by spend this month. Transfers move money between your own accounts
    # rather than spending it, so they're excluded the same way category activity is.
    payee_totals: dict[str, dict[str, float]] = {}
    for t in transactions:
        if t.transfer_account_id or t.amount >= 0:
            continue
        payee = payee_totals.setdefault(t.payee_name or "Unknown", {"spent_mu": 0, "count": 0})
        payee["spent_mu"] += abs(t.amount)
        payee["count"] += 1

    top_payees = [
        {
            "name": name,
            "spent": milliunits_to_dollars(v["spent_mu"]),
            "transaction_count": v["count"],
        }
        for name, v in sorted(payee_totals.items(), key=lambda kv: kv[1]["spent_mu"], reverse=True)[:top_n]
    ]

    # Trend uses each month's whole-budget totals (income/activity from list_months),
    # not the filtered, category-level totals above — getting the same exclusions for
    # every historical month would mean fetching each month's full category detail
    # instead of one cheap summary call per month. Income and net direction match;
    # spending here also includes credit-card payments and internal transfers.
    # `[-trend_months:]` would silently return everything for trend_months <= 0
    # (Python's `[-0:]` is `[0:]`, and a negative count slices from the front), so
    # a non-positive count is handled explicitly instead of relying on the slice.
    months_in_range = sorted((m for m in all_months if m.month <= month), key=lambda m: m.month)
    recent_months = months_in_range[-trend_months:] if trend_months > 0 else []
    trend = [
        {
            "month": m.month,
            "income": milliunits_to_dollars(abs(m.income)),
            "spent": milliunits_to_dollars(abs(m.activity)),
            "net": milliunits_to_dollars(abs(m.income) + m.activity),
        }
        for m in recent_months
    ]

    result = {
        "month": month,
        "summary": {
            "income": milliunits_to_dollars(income_mu),
            "spent": milliunits_to_dollars(spent_mu),
            "net": milliunits_to_dollars(net_mu),
            "savings_rate_pct": savings_rate,
            "age_of_money": month_detail.age_of_money,
            "overspent_category_count": len(overspent),
            "overspent_total": round(sum(o["overspent_by"] for o in overspent), 3),
        },
        "category_groups": category_groups,
        "top_categories": top_categories,
        "overspent_categories": overspent,
        "top_payees": top_payees,
        "trend": trend,
    }
    return json.dumps(result, indent=2)
