"""ASGI app that serves the MCP server over Streamable HTTP.

Used for remote deployment (e.g. behind a Cloudflare Container/Worker), as
opposed to the stdio transport used by ``python -m src.server`` for local
clients like Claude Desktop. Run with:

    uv run uvicorn src.server.http:app --host 0.0.0.0 --port 8080

Requires YNAB_API_KEY and MCP_AUTH_TOKEN in the environment. MCP_AUTH_TOKEN
gates every request under the MCP path, since this transport is reachable
over the network rather than a local pipe. It's checked against either an
`Authorization: Bearer <token>` header or a `?token=<token>` query parameter
— the query parameter exists because, as of this writing, Claude.ai's custom
connector UI has no field for a static header, only OAuth (see
https://github.com/anthropics/claude-ai-mcp/issues/112), so the token has to
travel in the URL you paste into that UI.
"""

import hmac

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

import src.server  # noqa: F401  registers all @mcp.tool() definitions
from src.config import Settings
from src.server._shared import mcp

MCP_PATH = "/mcp"


class BearerTokenMiddleware:
    """Requires the configured token on protected paths.

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

        request = Request(scope)
        scheme, _, presented = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            presented = request.query_params.get("token", "")

        if not presented or not hmac.compare_digest(presented, self.token):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def _health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def create_app() -> Starlette:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as e:
        raise RuntimeError(f"Invalid configuration: {e}") from e

    if not settings.mcp_auth_token:
        raise RuntimeError(
            "MCP_AUTH_TOKEN must be set to run the streamable-http transport; "
            "it is the only thing standing between your YNAB data and anyone "
            "who finds the URL."
        )

    # host="0.0.0.0": the MCP SDK auto-enables DNS-rebinding Host-header checks
    # (allowing only localhost) when host is 127.0.0.1/localhost/::1, which is
    # wrong once the server is reachable over the network via a container/Worker
    # rather than loopback. The bearer token below is the real access control here.
    app = mcp.streamable_http_app(streamable_http_path=MCP_PATH, host="0.0.0.0")
    app.router.routes.append(Route("/health", _health))
    app.add_middleware(BearerTokenMiddleware, token=settings.mcp_auth_token, protected_path=MCP_PATH)
    return app


app = create_app()
