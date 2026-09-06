"""Tests for src/server/reconcile.py (export_transactions_csv, reconcile_account)."""

import csv
import io
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Account, Transaction

CACHE_PATH = "src.server._shared.cache"
DB_PATH = "src.server._shared._ensure_db"


@pytest.fixture
def mock_cache():
    with patch(CACHE_PATH) as mock, patch(DB_PATH, new_callable=AsyncMock):
        yield mock


def _txn(**overrides) -> Transaction:
    defaults = {
        "id": "txn-1",
        "date": "2026-03-10",
        "amount": -50000,
        "cleared": "cleared",
        "approved": True,
        "account_id": "acc-1",
        "account_name": "Checking",
        "payee_name": "Coffee Shop",
        "category_name": "Dining Out",
    }
    return Transaction(**{**defaults, **overrides})


def _account(**overrides) -> Account:
    defaults = {"id": "acc-1", "name": "Checking", "type": "checking"}
    return Account(**{**defaults, **overrides})


# ── export_transactions_csv ─────────────────────────────────────


class TestExportTransactionsCsv:
    @pytest.mark.asyncio
    async def test_exports_expected_columns_and_amounts(self, mock_cache):
        from src.server import export_transactions_csv

        mock_cache.get_transactions_by_account = AsyncMock(return_value=[
            _txn(id="t1", amount=-50000, memo="latte"),
            _txn(id="t2", amount=125000, payee_name="Employer", category_name=None),
        ])
        result = await export_transactions_csv(plan_id="bud-1", account_id="acc-1")

        rows = list(csv.reader(io.StringIO(result)))
        header, row1, row2 = rows[0], rows[1], rows[2]
        assert header == [
            "Account", "Date", "Payee", "Category", "Memo",
            "Outflow", "Inflow", "Cleared", "Approved", "Flag",
        ]
        assert row1[5:8] == ["50.00", "", "cleared"]  # outflow
        assert row2[5:8] == ["", "125.00", "cleared"]  # inflow

    @pytest.mark.asyncio
    async def test_excludes_deleted_and_filters_by_until_date_and_cleared(self, mock_cache):
        from src.server import export_transactions_csv

        mock_cache.get_transactions = AsyncMock(return_value=[
            _txn(id="keep", date="2026-03-01", cleared="cleared"),
            _txn(id="too-late", date="2026-04-01", cleared="cleared"),
            _txn(id="wrong-status", date="2026-03-02", cleared="uncleared"),
            _txn(id="deleted", date="2026-03-01", cleared="cleared", deleted=True),
        ])
        result = await export_transactions_csv(
            plan_id="bud-1", until_date="2026-03-31", cleared="cleared"
        )
        rows = list(csv.reader(io.StringIO(result)))
        ids_present = [r[1] for r in rows[1:]]  # date column, only "keep" has 2026-03-01 among survivors
        assert len(rows) == 2  # header + one surviving row
        assert ids_present == ["2026-03-01"]

    @pytest.mark.asyncio
    async def test_guards_against_csv_formula_injection(self, mock_cache):
        from src.server import export_transactions_csv

        mock_cache.get_transactions_by_account = AsyncMock(return_value=[
            _txn(payee_name="=cmd|'/bin/sh'!A1", memo="+1+1"),
        ])
        result = await export_transactions_csv(plan_id="bud-1", account_id="acc-1")
        rows = list(csv.reader(io.StringIO(result)))
        payee_cell, memo_cell = rows[1][2], rows[1][4]
        assert payee_cell.startswith("'=")
        assert memo_cell.startswith("'+")


# ── reconcile_account ────────────────────────────────────────────


class TestReconcileAccount:
    @pytest.mark.asyncio
    async def test_dry_run_previews_without_mutating(self, mock_cache):
        from src.server import reconcile_account

        mock_cache.get_account = AsyncMock(return_value=_account())
        mock_cache.get_transactions_by_account = AsyncMock(return_value=[
            _txn(id="t1", date="2026-03-05", amount=-50000, cleared="cleared"),
            _txn(id="t2", date="2026-03-06", amount=-25000, cleared="uncleared"),  # excluded: not cleared
            _txn(id="t3", date="2026-04-01", amount=-99999, cleared="cleared"),  # excluded: after statement date
        ])
        mock_cache.create_transaction = AsyncMock()
        mock_cache.update_transactions = AsyncMock()

        result = json.loads(await reconcile_account(
            plan_id="bud-1", account_id="acc-1",
            statement_balance=-40.0, statement_date="2026-03-31",
        ))

        assert result["dry_run"] is True
        assert result["computed_cleared_balance"] == -50.0
        assert result["difference"] == 10.0  # -40 - (-50)
        assert result["transactions_to_mark_reconciled"] == 1
        assert result["adjustment_needed"] is True
        mock_cache.create_transaction.assert_not_called()
        mock_cache.update_transactions.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_creates_adjustment_and_marks_reconciled(self, mock_cache):
        from src.server import reconcile_account

        mock_cache.get_account = AsyncMock(return_value=_account())
        mock_cache.get_transactions_by_account = AsyncMock(return_value=[
            _txn(id="t1", date="2026-03-05", amount=-50000, cleared="cleared"),
            _txn(id="t2", date="2026-03-06", amount=-10000, cleared="reconciled"),  # already reconciled
        ])
        mock_cache.create_transaction = AsyncMock(return_value=_txn(id="adj-1"))
        mock_cache.update_transactions = AsyncMock(return_value=[])

        result = json.loads(await reconcile_account(
            plan_id="bud-1", account_id="acc-1",
            statement_balance=-55.0, statement_date="2026-03-31", confirm=True,
        ))

        assert result["dry_run"] is False
        assert result["adjustment_transaction_id"] == "adj-1"
        assert result["transactions_marked_reconciled"] == 1

        create_call = mock_cache.create_transaction.call_args[0][0]
        assert create_call["account_id"] == "acc-1"
        assert create_call["cleared"] == "reconciled"
        # computed cleared balance is -50000 + -10000 (t1 "cleared" + t2 already "reconciled",
        # both count toward the balance even though only t1 still needs marking)
        assert create_call["amount"] == -55000 - (-60000)

        update_call = mock_cache.update_transactions.call_args[0][0]
        assert update_call == [{"id": "t1", "cleared": "reconciled"}]

    @pytest.mark.asyncio
    async def test_confirm_with_nothing_to_do_makes_no_api_calls(self, mock_cache):
        from src.server import reconcile_account

        mock_cache.get_account = AsyncMock(return_value=_account())
        mock_cache.get_transactions_by_account = AsyncMock(return_value=[
            _txn(id="t1", date="2026-03-05", amount=-50000, cleared="reconciled"),
        ])
        mock_cache.create_transaction = AsyncMock()
        mock_cache.update_transactions = AsyncMock()

        result = json.loads(await reconcile_account(
            plan_id="bud-1", account_id="acc-1",
            statement_balance=-50.0, statement_date="2026-03-31", confirm=True,
        ))

        assert result["adjustment_transaction_id"] is None
        assert result["transactions_marked_reconciled"] == 0
        mock_cache.create_transaction.assert_not_called()
        mock_cache.update_transactions.assert_not_called()
