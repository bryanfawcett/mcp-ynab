import csv
import io
import json
from datetime import date

from src.models.common import milliunits_to_dollars
from src.server import _shared, icons
from src.server._shared import dollars_to_milliunits

CLEARED_STATUSES = {"cleared", "reconciled"}

# Cell values starting with these are formulas to a spreadsheet app (Excel,
# Google Sheets) that opens this CSV — a payee/memo/category name that
# happens to start with one would otherwise execute as a formula instead of
# showing as text. Payee/memo/category names are the user's own YNAB data,
# not attacker input, but a shared/joint budget or a scanned-receipt import
# can still produce one, and the fix is a single prefixed apostrophe.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    if value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _resolve_date(value: str) -> str:
    if value == "today":
        return date.today().strftime("%Y-%m-%d")
    return value


@_shared.mcp.tool(icons=[icons.TRANSACTION])
@_shared.handle_errors
async def export_transactions_csv(
    plan_id: str,
    account_id: str | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
    cleared: str | None = None,
) -> str:
    """Export transactions as CSV text — for reviewing against a bank statement,
    opening in a spreadsheet, or handing to another tool. Not a file: the CSV
    text comes back directly as the tool result.

    Columns: Account, Date, Payee, Category, Memo, Outflow, Inflow, Cleared,
    Approved, Flag. Outflow/Inflow are separate columns (like YNAB's own
    register export) rather than one signed Amount column, matching how a
    paper/PDF bank statement usually lists debits and credits.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        account_id: Only export this account's transactions (all accounts if omitted)
        since_date: Only include transactions on or after this date (YYYY-MM-DD)
        until_date: Only include transactions on or before this date (YYYY-MM-DD) —
            e.g. a statement's closing date
        cleared: Only include transactions with this cleared status
            ('cleared', 'uncleared', or 'reconciled') — all statuses if omitted
    """
    if account_id:
        transactions = await _shared.cache.get_transactions_by_account(account_id, plan_id, since_date)
    else:
        transactions = await _shared.cache.get_transactions(plan_id, since_date)

    rows = [
        t for t in transactions
        if not t.deleted
        and (until_date is None or t.date <= until_date)
        and (cleared is None or t.cleared == cleared)
    ]
    rows.sort(key=lambda t: (t.date, t.id))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Account", "Date", "Payee", "Category", "Memo", "Outflow", "Inflow", "Cleared", "Approved", "Flag"])
    for t in rows:
        amount = milliunits_to_dollars(t.amount)
        outflow = f"{-amount:.2f}" if amount < 0 else ""
        inflow = f"{amount:.2f}" if amount > 0 else ""
        writer.writerow([
            _csv_safe(t.account_name or ""),
            t.date,
            _csv_safe(t.payee_name or ""),
            _csv_safe(t.category_name or ""),
            _csv_safe(t.memo or ""),
            outflow,
            inflow,
            t.cleared,
            "yes" if t.approved else "no",
            t.flag_color or "",
        ])
    return buffer.getvalue()


@_shared.mcp.tool(icons=[icons.RECONCILE])
@_shared.handle_errors
async def reconcile_account(
    plan_id: str,
    account_id: str,
    statement_balance: float,
    statement_date: str = "today",
    confirm: bool = False,
) -> str:
    """Reconcile an account against a real-world statement balance — the same
    workflow as YNAB's own "Reconcile" button: compare the account's cleared
    transactions (as of a date) against the statement, add an adjustment
    transaction for any difference, and mark those transactions reconciled
    (locked from further changes in the YNAB app, same as a normal reconcile).

    Defaults to a dry run (confirm=False): returns what *would* happen —
    the computed cleared balance, the difference from your statement, how many
    transactions would be marked reconciled, and whether an adjustment
    transaction would be created — without changing anything. Review that
    output, then call again with confirm=True to actually apply it. This is
    a hard-to-reverse action (reconciled transactions are locked in the YNAB
    app; un-reconciling requires a normal app edit), so always dry-run first.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        account_id: The account to reconcile
        statement_balance: The real-world balance from your bank statement, in dollars
        statement_date: The statement's date/cutoff (YYYY-MM-DD) or 'today' — only
            transactions on or before this date are considered
        confirm: Set true to actually create the adjustment and mark transactions
            reconciled. False (default) previews the outcome without changing anything.
    """
    statement_date = _resolve_date(statement_date)
    account = await _shared.cache.get_account(account_id, plan_id)
    all_transactions = await _shared.cache.get_transactions_by_account(account_id, plan_id)

    cleared_as_of_statement = [
        t for t in all_transactions
        if not t.deleted and t.cleared in CLEARED_STATUSES and t.date <= statement_date
    ]
    computed_cleared_balance_mu = sum(t.amount for t in cleared_as_of_statement)
    statement_balance_mu = dollars_to_milliunits(statement_balance)
    difference_mu = statement_balance_mu - computed_cleared_balance_mu

    to_mark_reconciled = [t for t in cleared_as_of_statement if t.cleared == "cleared"]

    result = {
        "account_id": account_id,
        "account_name": account.name,
        "statement_date": statement_date,
        "statement_balance": round(statement_balance, 2),
        "computed_cleared_balance": milliunits_to_dollars(computed_cleared_balance_mu),
        "difference": milliunits_to_dollars(difference_mu),
        "transactions_to_mark_reconciled": len(to_mark_reconciled),
        "adjustment_needed": difference_mu != 0,
    }

    if not confirm:
        result["dry_run"] = True
        result["next_step"] = (
            "Call again with confirm=true to apply this — creates the adjustment "
            "transaction (if any) and marks the listed transactions reconciled."
            if (difference_mu != 0 or to_mark_reconciled)
            else "Already reconciled as of this date — nothing to do."
        )
        return json.dumps(result, indent=2)

    adjustment = None
    if difference_mu != 0:
        adjustment_txn = {
            "account_id": account_id,
            "date": statement_date,
            "amount": difference_mu,
            "payee_name": "Reconciliation Balance Adjustment",
            "cleared": "reconciled",
            "approved": True,
        }
        adjustment = await _shared.cache.create_transaction(adjustment_txn, plan_id)

    if to_mark_reconciled:
        await _shared.cache.update_transactions(
            [{"id": t.id, "cleared": "reconciled"} for t in to_mark_reconciled],
            plan_id,
        )

    result["dry_run"] = False
    result["adjustment_transaction_id"] = adjustment.id if adjustment else None
    result["transactions_marked_reconciled"] = len(to_mark_reconciled)
    return json.dumps(result, indent=2)
