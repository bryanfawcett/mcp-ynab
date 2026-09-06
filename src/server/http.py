"""ASGI app that serves the MCP server over Streamable HTTP.

Used for remote deployment (e.g. behind a Cloudflare Container/Worker), as
opposed to the stdio transport used by ``python -m src.server`` for local
clients like Claude Desktop. Run with:

    uv run uvicorn src.server.http:app --host 0.0.0.0 --port 8080

Two deployment modes, controlled by MCP_MULTI_TENANT:

- **Single-tenant** (default, MCP_MULTI_TENANT unset): one YNAB_API_KEY for
  the whole deployment, gated by a separate MCP_AUTH_TOKEN shared secret. For
  someone deploying a private instance for just themselves.
- **Multi-tenant** (MCP_MULTI_TENANT=true): no fixed YNAB_API_KEY. Instead,
  the bearer token/query token on each request *is* that caller's own YNAB
  personal access token, resolved to a per-caller YNABClient/CacheService/
  SQLite cache file for the duration of the request — so one deployment can
  be shared publicly and each person only ever sees their own budget. For a
  deployment meant to be used by more than just its operator (see README.md).

Either way, the token is accepted as an `Authorization: Bearer <token>`
header or a `?token=<token>` query parameter — the query parameter exists
because, as of this writing, Claude.ai's custom connector UI has no field for
a static header, only OAuth (see
https://github.com/anthropics/claude-ai-mcp/issues/112), so the token has to
travel in the URL you paste into that UI.
"""

import hashlib
import hmac
from collections import OrderedDict
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

import src.server  # noqa: F401  registers all @mcp.tool() definitions
from src.cache.service import CacheService
from src.config import Settings
from src.server import _shared
from src.server._shared import mcp
from src.server.oauth import OAuthProxy, build_oauth_proxy
from src.ynab_client import YNABClient

MCP_PATH = "/mcp"

# Bounds the multi-tenant registry's in-memory YNABClient/CacheService pairs
# and their SQLite cache files — a lot more than this server would realistically
# see distinct callers between container idle-sleeps, so it's a hygiene cap
# against abuse rather than a real expected ceiling.
MAX_TENANTS = 200


def _presented_token(request: Request) -> str:
    scheme, _, presented = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer":
        return presented
    return request.query_params.get("token", "")


class BearerTokenMiddleware:
    """Single-tenant mode: requires the one configured MCP_AUTH_TOKEN.

    Accepted as either an `Authorization: Bearer <token>` header (what any
    proper MCP client sends) or a `?token=<token>` query parameter (for
    clients, like Claude.ai's custom connector UI, that only let you supply a
    URL — see the module docstring).
    """

    def __init__(self, app: ASGIApp, token: str, protected_path: str) -> None:
        self.app = app
        self.token = token
        self.protected_path = protected_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.protected_path):
            await self.app(scope, receive, send)
            return

        presented = _presented_token(Request(scope))
        if not presented or not hmac.compare_digest(presented, self.token):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class TenantRegistry:
    """Per-token YNABClient/CacheService/SQLite-file, for multi-tenant mode.

    Keyed by a hash of the presented token rather than the token itself, so a
    raw YNAB personal access token is never retained as a dict key. Bounded
    LRU: once MAX_TENANTS distinct tokens have been seen, the oldest is
    evicted (and its YNABClient's connection pool closed) to make room.
    """

    def __init__(self, settings: Settings, cache_dir: Path):
        self._settings = settings
        self._cache_dir = cache_dir
        self._entries: OrderedDict[str, tuple[YNABClient, CacheService, str]] = OrderedDict()

    @staticmethod
    def _tenant_id(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()[:16]

    async def get_or_create(self, token: str) -> tuple[YNABClient, CacheService, str]:
        tenant_id = self._tenant_id(token)
        entry = self._entries.get(tenant_id)
        if entry is not None:
            self._entries.move_to_end(tenant_id)
            return entry

        tenant_client = YNABClient(token, timeout=self._settings.http_timeout)
        tenant_cache = CacheService(tenant_client, self._settings)
        db_path = str(self._cache_dir / f"tenant-{tenant_id}.db")
        entry = (tenant_client, tenant_cache, db_path)
        self._entries[tenant_id] = entry

        if len(self._entries) > MAX_TENANTS:
            _, (evicted_client, _, _) = self._entries.popitem(last=False)
            await evicted_client.close()

        return entry


class MultiTenantMiddleware:
    """Multi-tenant mode: the presented token *is* the caller's own YNAB
    personal access token — resolved to that caller's own YNABClient/
    CacheService/cache file for the duration of the request, so every tool
    call this request makes (via src.server._shared's contextvar-backed
    `client`/`cache`) only ever touches that one person's budget.

    Doesn't validate the token against YNAB up front: an invalid one simply
    fails naturally on the first real API call, the same YNABError path every
    other auth failure already goes through.
    """

    def __init__(
        self, app: ASGIApp, registry: TenantRegistry, protected_path: str, oauth_proxy: OAuthProxy | None = None
    ) -> None:
        self.app = app
        self.registry = registry
        self.protected_path = protected_path
        self.oauth_proxy = oauth_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.protected_path):
            await self.app(scope, receive, send)
            return

        presented = _presented_token(Request(scope))
        if not presented:
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "hint": "Use your own YNAB personal access token as the bearer token "
                    "(or ?token= query param) — see https://app.ynab.com/settings/developer.",
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        # If OAuth is configured and `presented` is one of its own opaque
        # access tokens, this resolves to the underlying YNAB access token
        # (refreshing it first if needed); otherwise it's returned unchanged
        # — `presented` *is* the caller's own YNAB personal access token, as
        # in the PAT-only flow.
        if self.oauth_proxy is not None:
            presented = await self.oauth_proxy.resolve_token(presented)

        tenant_client, tenant_cache, db_path = await self.registry.get_or_create(presented)
        tokens = _shared.activate_tenant(tenant_client, tenant_cache, db_path)
        try:
            await self.app(scope, receive, send)
        finally:
            _shared.deactivate_tenant(tokens)


async def _health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def create_app() -> Starlette:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as e:
        raise RuntimeError(f"Invalid configuration: {e}") from e

    # host="0.0.0.0": the MCP SDK auto-enables DNS-rebinding Host-header checks
    # (allowing only localhost) when host is 127.0.0.1/localhost/::1, which is
    # wrong once the server is reachable over the network via a container/Worker
    # rather than loopback. The auth layer below is the real access control here.
    #
    # stateless_http=True: in the SDK's default *stateful* mode, the first
    # request to a session spawns a long-lived task that serves every later
    # request carrying that Mcp-Session-Id, and that task permanently captures
    # whichever contextvars (see _shared.py's activate_tenant/_TenantProxy)
    # were active on the *creating* request. In single-tenant mode that's
    # harmless (one shared client either way), but in multi-tenant mode it
    # means every later request for that session runs tool calls as whichever
    # caller happened to create it — regardless of the token *that* request
    # presents. The SDK has a same-credential guard for this, but it keys off
    # `scope["user"]` being an `AuthenticatedUser` set by the SDK's own OAuth
    # middleware, which this app doesn't use, so the guard is always a no-op
    # here. stateless_http=True sidesteps the whole issue: every request gets
    # its own fresh transport/task, so it always runs under its own request's
    # contextvars — confirmed with a live client (init + a separate tools/list
    # call both succeed with no session continuity needed).
    app = mcp.streamable_http_app(streamable_http_path=MCP_PATH, host="0.0.0.0", stateless_http=True)
    app.router.routes.append(Route("/health", _health))

    if settings.multi_tenant:
        cache_dir = Path(settings.cache_db_path).parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        registry = TenantRegistry(settings, cache_dir)
        # None (the default) when YNAB_OAUTH_CLIENT_ID/SECRET aren't set —
        # the PAT-only flow is unaffected either way. See src/server/oauth.py.
        oauth_proxy = build_oauth_proxy(settings)
        if oauth_proxy is not None:
            app.router.routes.extend(oauth_proxy.routes())
        app.add_middleware(MultiTenantMiddleware, registry=registry, protected_path=MCP_PATH, oauth_proxy=oauth_proxy)
    else:
        if not settings.mcp_auth_token:
            raise RuntimeError(
                "MCP_AUTH_TOKEN must be set to run the streamable-http transport in "
                "single-tenant mode; it is the only thing standing between your YNAB "
                "data and anyone who finds the URL. (Set MCP_MULTI_TENANT=true instead "
                "if this deployment should let multiple people each use their own YNAB "
                "account — see README.md.)"
            )
        app.add_middleware(BearerTokenMiddleware, token=settings.mcp_auth_token, protected_path=MCP_PATH)

    return app


app = create_app()
