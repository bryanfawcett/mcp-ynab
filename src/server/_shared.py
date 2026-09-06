import contextvars
import json
import logging
import sys
from functools import wraps

import httpx
from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

from src.cache.service import CacheService
from src.config import Settings
from src.db.engine import current_db_path, init_db, reset_db_path, use_db_path
from src.server import icons
from src.models.account import ACCOUNT_DEFAULT_EXCLUDE, Account
from src.models.category import (
    CATEGORY_DEFAULT_EXCLUDE,
    CATEGORY_GROUP_DEFAULT_EXCLUDE,
    Category,
    CategoryGroup,
)
from src.models.common import YNABBaseModel
from src.models.money_movement import (
    MONEY_MOVEMENT_DEFAULT_EXCLUDE,
    MONEY_MOVEMENT_GROUP_DEFAULT_EXCLUDE,
    MoneyMovement,
    MoneyMovementGroup,
)
from src.models.month import MONTH_DEFAULT_EXCLUDE, MonthDetail, MonthSummary
from src.models.payee import PAYEE_DEFAULT_EXCLUDE, Payee
from src.models.payee_location import PAYEE_LOCATION_DEFAULT_EXCLUDE, PayeeLocation
from src.models.plan import PLAN_DEFAULT_EXCLUDE, PlanDetail, PlanSettings, PlanSummary
from src.models.scheduled_transaction import (
    SCHEDULED_SUBTRANSACTION_DEFAULT_EXCLUDE,
    SCHEDULED_TRANSACTION_DEFAULT_EXCLUDE,
    ScheduledSubtransaction,
    ScheduledTransaction,
)
from src.models.transaction import (
    SUBTRANSACTION_DEFAULT_EXCLUDE,
    TRANSACTION_DEFAULT_EXCLUDE,
    HybridTransaction,
    Subtransaction,
    Transaction,
)
from src.models.user import User
from src.ynab_client import YNABClient, YNABError

try:
    settings = Settings()  # type: ignore[call-arg]
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

if not settings.multi_tenant and not settings.ynab_api_key:
    print(
        "ERROR: YNAB_API_KEY is required unless MCP_MULTI_TENANT is set.",
        file=sys.stderr,
    )
    sys.exit(1)

mcp = MCPServer("ynab", title="YNAB", icons=[icons.SERVER])

# In multi-tenant mode (src/server/http.py), every tool call is made on behalf
# of whichever caller's YNAB token the current request is scoped to, not one
# fixed account — so `client`/`cache` below are proxies that resolve to that
# request's own instances via contextvars, falling back to the single
# process-wide instances (built from YNAB_API_KEY) that stdio mode and
# single-tenant HTTP deployments use unconditionally.
_tenant_client: contextvars.ContextVar["YNABClient | None"] = contextvars.ContextVar(
    "tenant_client", default=None
)
_tenant_cache: contextvars.ContextVar["CacheService | None"] = contextvars.ContextVar(
    "tenant_cache", default=None
)

_default_client = YNABClient(settings.ynab_api_key, timeout=settings.http_timeout) if settings.ynab_api_key else None
_default_cache = CacheService(_default_client, settings) if _default_client else None


class _TenantProxy:
    """Delegates attribute access to the current request's tenant instance.

    Every tool module does `_shared.client.foo()` / `_shared.cache.foo()` as a
    fresh attribute lookup on each call, so swapping what these two names
    resolve to per-request (via contextvars, which are asyncio-task-local) is
    enough to make every existing tool multi-tenant-safe with no changes to
    the ~15 tool modules themselves.
    """

    def __init__(self, ctx_var: "contextvars.ContextVar", default):
        object.__setattr__(self, "_ctx_var", ctx_var)
        object.__setattr__(self, "_default", default)

    def __getattr__(self, name):
        current = self._ctx_var.get()
        instance = current if current is not None else self._default
        if instance is None:
            raise RuntimeError(
                "No YNAB client for this request. In multi-tenant mode this means "
                "the request wasn't authenticated with a tenant token before reaching "
                "the tool — check src/server/http.py's middleware."
            )
        return getattr(instance, name)


client = _TenantProxy(_tenant_client, _default_client)
cache = _TenantProxy(_tenant_cache, _default_cache)


def activate_tenant(
    tenant_client: YNABClient, tenant_cache: CacheService, db_path: str
) -> tuple[contextvars.Token, contextvars.Token, contextvars.Token]:
    """Scope `client`/`cache`/the SQLite cache DB to one tenant for this task.

    Used by src/server/http.py's multi-tenant middleware, once per request.
    Returns the tokens needed to undo it via deactivate_tenant — always in a
    `finally`, since these contextvars are asyncio-task-local and leaking a
    stale value would only affect this one request's task, but should still
    be cleaned up.
    """
    return (
        _tenant_client.set(tenant_client),
        _tenant_cache.set(tenant_cache),
        use_db_path(db_path),
    )


def deactivate_tenant(tokens: tuple[contextvars.Token, contextvars.Token, contextvars.Token]) -> None:
    client_token, cache_token, db_token = tokens
    _tenant_client.reset(client_token)
    _tenant_cache.reset(cache_token)
    reset_db_path(db_token)


# Default exclude sets per model. Used when a tool is called without an explicit
# `exclude_fields` argument. See FIELDS.md for the full list per model.
DEFAULT_EXCLUDES: dict[type[YNABBaseModel], set[str]] = {
    Account: ACCOUNT_DEFAULT_EXCLUDE,
    Category: CATEGORY_DEFAULT_EXCLUDE,
    CategoryGroup: CATEGORY_GROUP_DEFAULT_EXCLUDE,
    HybridTransaction: TRANSACTION_DEFAULT_EXCLUDE,
    MoneyMovement: MONEY_MOVEMENT_DEFAULT_EXCLUDE,
    MoneyMovementGroup: MONEY_MOVEMENT_GROUP_DEFAULT_EXCLUDE,
    MonthDetail: MONTH_DEFAULT_EXCLUDE,
    MonthSummary: MONTH_DEFAULT_EXCLUDE,
    Payee: PAYEE_DEFAULT_EXCLUDE,
    PayeeLocation: PAYEE_LOCATION_DEFAULT_EXCLUDE,
    PlanDetail: PLAN_DEFAULT_EXCLUDE,
    PlanSettings: set(),
    PlanSummary: PLAN_DEFAULT_EXCLUDE,
    ScheduledSubtransaction: SCHEDULED_SUBTRANSACTION_DEFAULT_EXCLUDE,
    ScheduledTransaction: SCHEDULED_TRANSACTION_DEFAULT_EXCLUDE,
    Subtransaction: SUBTRANSACTION_DEFAULT_EXCLUDE,
    Transaction: TRANSACTION_DEFAULT_EXCLUDE,
    User: set(),
}


def dollars_to_milliunits(amount: float) -> int:
    """Convert a dollar amount to YNAB milliunits (1000 = $1.00)."""
    return round(amount * 1000)


# Nested default excludes: when a parent model contains a list of nested models,
# the nested model's default excludes need to be applied explicitly because
# Pydantic's model_dump(exclude=set) only handles top-level fields.
NESTED_DEFAULT_EXCLUDES: dict[type[YNABBaseModel], dict[str, type[YNABBaseModel]]] = {
    CategoryGroup: {"categories": Category},
    MonthDetail: {"categories": Category},
}


def _resolve_exclude(
    model_class: type[YNABBaseModel], exclude_fields: list[str] | None
) -> set[str] | dict[str, object]:
    """Pick the exclude for a model.

    Top-level uses the caller's exclude_fields if provided, otherwise the model
    default. Nested defaults (per NESTED_DEFAULT_EXCLUDES) always apply so the
    nested-model defaults aren't dropped when a caller customizes top-level.
    """
    if exclude_fields is None:
        top_level: set[str] = DEFAULT_EXCLUDES.get(model_class, set())
    else:
        top_level = set(exclude_fields)

    nested = NESTED_DEFAULT_EXCLUDES.get(model_class)
    if not nested:
        return top_level

    exclude: dict[str, object] = {f: True for f in top_level}
    for field_name, nested_class in nested.items():
        nested_default = DEFAULT_EXCLUDES.get(nested_class, set())
        if nested_default:
            exclude[field_name] = {"__all__": nested_default}
    return exclude


def serialize(model, *, exclude_fields: list[str] | None = None) -> str:
    """Serialize a Pydantic model to a JSON string.

    By default, excludes the model's standard noisy/rarely-used fields. Pass
    `exclude_fields=[]` to return all fields, or a custom list to override.
    """
    exclude = _resolve_exclude(type(model), exclude_fields)
    return json.dumps(
        model.model_dump(by_alias=True, mode="json", exclude=exclude), indent=2
    )


def serialize_list(models, *, exclude_fields: list[str] | None = None) -> str:
    """Serialize a list of Pydantic models to a JSON string.

    By default, excludes the model's standard noisy/rarely-used fields. Pass
    `exclude_fields=[]` to return all fields, or a custom list to override.
    """
    if not models:
        return "[]"
    exclude = _resolve_exclude(type(models[0]), exclude_fields)
    return json.dumps(
        [m.model_dump(by_alias=True, mode="json", exclude=exclude) for m in models],
        indent=2,
    )


async def _ensure_db():
    # init_db is idempotent per path (a plain dict lookup after the first
    # call), so no separate "already initialized" flag is needed here — and
    # per-request paths (multi-tenant mode) couldn't share one anyway.
    await init_db(current_db_path() or settings.cache_db_path)


def handle_errors(func):
    """Decorator that catches YNAB and HTTP errors and returns friendly messages.

    Also logs each caught error server-side (tool name + error) before
    returning it to the caller — previously these were swallowed entirely
    into the tool's JSON return value, invisible on the server side even
    with observability enabled, since nothing ever reached stdout/stderr for
    Cloudflare's container logs (or a local terminal) to capture. This is
    the closest equivalent to a browser's devtools console for this
    deployment: `wrangler tail` or the Cloudflare dashboard's Logs tab for
    the live container shows these in real time; locally they print to
    stderr the same as any other Python logging call.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            await _ensure_db()
            return await func(*args, **kwargs)
        except YNABError as e:
            logger.error("%s: YNAB error %s: %s", func.__name__, e.status_code, e.message)
            return json.dumps({"error": e.message, "error_id": e.error_id, "status_code": e.status_code})
        except httpx.HTTPStatusError as e:
            logger.error("%s: HTTP %s: %s", func.__name__, e.response.status_code, e.response.text)
            return json.dumps({"error": f"HTTP {e.response.status_code}: {e.response.text}"})
        except httpx.RequestError as e:
            logger.error("%s: request failed: %s", func.__name__, e)
            return json.dumps({"error": f"Request failed: {e}"})

    return wrapper
