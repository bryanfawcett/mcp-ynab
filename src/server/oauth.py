"""OAuth 2.1 proxy: lets an MCP client "Sign in with YNAB" instead of the
caller pasting their own YNAB personal access token.

Deliberately NOT wired through the MCP SDK's `OAuthAuthorizationServerProvider`
machinery (mcp.server.auth.provider) even though that Protocol exists for
exactly this shape of proxy -- adopting it means passing `auth_server_provider`
at `MCPServer(...)` construction time, and `src/server/_shared.py`'s `mcp`
instance is one shared singleton used by stdio mode and every HTTP mode
(single-tenant, multi-tenant-PAT) alike. Making that singleton's construction
depend on whether THIS deployment happens to have OAuth configured -- and
having the SDK's own bearer-auth enforcement apply unconditionally to every
mode as a result -- risks regressing the existing, tested PAT flow for a
proxy that only some deployments even use. Implementing the handful of routes
by hand instead keeps this fully additive: nothing here changes if
YNAB_OAUTH_CLIENT_ID/SECRET aren't set, and `resolve_token` (the one hook
into the existing multi-tenant flow) falls through to treating the presented
value as a raw PAT -- today's behavior -- whenever it isn't one of this
module's own tokens.

Two token exchanges happen, not one:
- This server <-> the MCP client: standard OAuth 2.1 + PKCE, since MCP
  clients are typically public clients that can't hold a secret.
- This server <-> YNAB: the Authorization Code Grant YNAB documents
  (https://api.ynab.com), using YNAB_OAUTH_CLIENT_ID/SECRET as a confidential
  client. PKCE isn't needed for this leg (this server holds a secret), so it
  isn't used here.

Every authorization code, access token, and refresh token this module issues
is opaque and random (`secrets.token_urlsafe`) -- never the underlying YNAB
token, which stays in KV and is only ever sent to YNAB itself.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from src.config import Settings
from src.server.oauth_kv import KVStore

YNAB_AUTHORIZE_URL = "https://app.ynab.com/oauth/authorize"
YNAB_TOKEN_URL = "https://app.ynab.com/oauth/token"

# How long a caller's own access token (the opaque value we hand them) is
# valid for before they must use their refresh token. Shorter than YNAB's own
# ~7200s window so a client refreshes with us well before the underlying YNAB
# token would expire on its own.
ACCESS_TOKEN_TTL = 3600
AUTHORIZE_SESSION_TTL = 600  # time allowed to complete the YNAB redirect dance
AUTH_CODE_TTL = 120  # single-use, short-lived by design


def _opaque(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _pkce_matches(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method != "S256":
        return False
    digest = hashlib.sha256(code_verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(computed, code_challenge)


class OAuthProxy:
    """Holds the KV store and YNAB credentials; exposes the Starlette routes
    and the one hook (`resolve_token`) the multi-tenant middleware calls."""

    def __init__(self, settings: Settings, kv: KVStore, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._kv = kv
        self._http = http_client if http_client is not None else httpx.AsyncClient(timeout=settings.http_timeout)

    @property
    def callback_url(self) -> str:
        return f"{self._settings.oauth_issuer_url}/oauth/ynab/callback"

    # -- Dynamic client registration (RFC 7591) --------------------------

    async def register_client(self, request: Request) -> Response:
        body = await request.json()
        redirect_uris = body.get("redirect_uris")
        if not redirect_uris or not isinstance(redirect_uris, list):
            return JSONResponse({"error": "invalid_client_metadata", "error_description": "redirect_uris is required"}, status_code=400)

        client_id = _opaque("client")
        record = {
            "client_id": client_id,
            "redirect_uris": redirect_uris,
            "client_name": body.get("client_name"),
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "created_at": time.time(),
        }
        await self._kv.put_json(f"oauth:client:{client_id}", record)
        return JSONResponse({**record, "client_id_issued_at": int(record["created_at"])}, status_code=201)

    async def _get_client(self, client_id: str) -> dict[str, Any] | None:
        return await self._kv.get_json(f"oauth:client:{client_id}")

    # -- /oauth/authorize: start the dance, redirect to YNAB --------------

    async def authorize(self, request: Request) -> Response:
        params = request.query_params
        client_id = params.get("client_id", "")
        redirect_uri = params.get("redirect_uri", "")
        code_challenge = params.get("code_challenge", "")
        code_challenge_method = params.get("code_challenge_method", "")
        state = params.get("state", "")
        scope = params.get("scope", "")

        client = await self._get_client(client_id)
        if not client or redirect_uri not in client["redirect_uris"]:
            return JSONResponse({"error": "invalid_request", "error_description": "unknown client_id or redirect_uri"}, status_code=400)
        if not code_challenge or code_challenge_method != "S256":
            return JSONResponse({"error": "invalid_request", "error_description": "PKCE (S256) is required"}, status_code=400)

        session_id = _opaque("session")
        await self._kv.put_json(
            f"oauth:session:{session_id}",
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "state": state,
                "scope": scope,
            },
            expiration_ttl=AUTHORIZE_SESSION_TTL,
        )

        ynab_params = {
            "client_id": self._settings.ynab_oauth_client_id,
            "redirect_uri": self.callback_url,
            "response_type": "code",
            "state": session_id,
        }
        if scope == "read-only":
            ynab_params["scope"] = "read-only"
        return RedirectResponse(f"{YNAB_AUTHORIZE_URL}?{urlencode(ynab_params)}", status_code=302)

    # -- /oauth/ynab/callback: YNAB redirects back here --------------------

    async def ynab_callback(self, request: Request) -> Response:
        params = request.query_params
        session_id = params.get("state", "")
        ynab_code = params.get("code", "")
        if error := params.get("error"):
            return JSONResponse({"error": error, "error_description": params.get("error_description")}, status_code=400)

        session = await self._kv.get_json(f"oauth:session:{session_id}")
        if not session or not ynab_code:
            return JSONResponse({"error": "invalid_request", "error_description": "expired or unknown authorization session"}, status_code=400)

        try:
            response = await self._http.post(
                YNAB_TOKEN_URL,
                data={
                    "client_id": self._settings.ynab_oauth_client_id,
                    "client_secret": self._settings.ynab_oauth_client_secret,
                    "redirect_uri": self.callback_url,
                    "grant_type": "authorization_code",
                    "code": ynab_code,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            return JSONResponse({"error": "server_error", "error_description": f"YNAB token exchange failed: {e}"}, status_code=502)

        ynab_token = response.json()
        our_code = _opaque("code")
        await self._kv.put_json(
            f"oauth:code:{our_code}",
            {
                "client_id": session["client_id"],
                "redirect_uri": session["redirect_uri"],
                "code_challenge": session["code_challenge"],
                "scope": session["scope"],
                "ynab_access_token": ynab_token["access_token"],
                "ynab_refresh_token": ynab_token["refresh_token"],
                "ynab_expires_at": time.time() + ynab_token["expires_in"],
            },
            expiration_ttl=AUTH_CODE_TTL,
        )
        await self._kv.delete(f"oauth:session:{session_id}")

        redirect_params = {"code": our_code}
        if session["state"]:
            redirect_params["state"] = session["state"]
        return RedirectResponse(f"{session['redirect_uri']}?{urlencode(redirect_params)}", status_code=302)

    # -- /oauth/token: the MCP client exchanges a code or refresh token ----

    async def token(self, request: Request) -> Response:
        form = await request.form()
        grant_type = form.get("grant_type")

        if grant_type == "authorization_code":
            return await self._exchange_code(form)
        if grant_type == "refresh_token":
            return await self._exchange_refresh(form)
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    async def _exchange_code(self, form: Any) -> Response:
        code = str(form.get("code", ""))
        record = await self._kv.get_json(f"oauth:code:{code}")
        if not record:
            return JSONResponse({"error": "invalid_grant", "error_description": "unknown or expired code"}, status_code=400)
        # Single-use: delete immediately, before any other validation, so a
        # concurrent replay of the same code can't also succeed.
        await self._kv.delete(f"oauth:code:{code}")

        if str(form.get("redirect_uri", "")) != record["redirect_uri"]:
            return JSONResponse({"error": "invalid_grant", "error_description": "redirect_uri mismatch"}, status_code=400)
        code_verifier = str(form.get("code_verifier", ""))
        if not code_verifier or not _pkce_matches(code_verifier, record["code_challenge"], "S256"):
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

        return await self._issue_tokens(
            client_id=record["client_id"],
            scope=record["scope"],
            ynab_access_token=record["ynab_access_token"],
            ynab_refresh_token=record["ynab_refresh_token"],
            ynab_expires_at=record["ynab_expires_at"],
        )

    async def _exchange_refresh(self, form: Any) -> Response:
        refresh_token = str(form.get("refresh_token", ""))
        record = await self._kv.get_json(f"oauth:refresh:{refresh_token}")
        if not record:
            return JSONResponse({"error": "invalid_grant", "error_description": "unknown or revoked refresh token"}, status_code=400)

        ynab_access_token = record["ynab_access_token"]
        ynab_refresh_token = record["ynab_refresh_token"]
        ynab_expires_at = record["ynab_expires_at"]
        if time.time() >= ynab_expires_at - 60:
            refreshed = await self._refresh_ynab_token(ynab_refresh_token)
            if refreshed is None:
                return JSONResponse({"error": "invalid_grant", "error_description": "YNAB refresh token is no longer valid"}, status_code=400)
            ynab_access_token, ynab_refresh_token, ynab_expires_at = refreshed

        # Rotate: the old refresh token record is replaced by a fresh one
        # tied to the new access token, so a leaked old refresh token stops
        # working the moment it's used once.
        await self._kv.delete(f"oauth:refresh:{refresh_token}")
        return await self._issue_tokens(
            client_id=record["client_id"],
            scope=record["scope"],
            ynab_access_token=ynab_access_token,
            ynab_refresh_token=ynab_refresh_token,
            ynab_expires_at=ynab_expires_at,
        )

    async def _refresh_ynab_token(self, ynab_refresh_token: str) -> tuple[str, str, float] | None:
        try:
            response = await self._http.post(
                YNAB_TOKEN_URL,
                data={
                    "client_id": self._settings.ynab_oauth_client_id,
                    "client_secret": self._settings.ynab_oauth_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": ynab_refresh_token,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        payload = response.json()
        return payload["access_token"], payload["refresh_token"], time.time() + payload["expires_in"]

    async def _issue_tokens(
        self, *, client_id: str, scope: str, ynab_access_token: str, ynab_refresh_token: str, ynab_expires_at: float
    ) -> Response:
        access_token = _opaque("at")
        refresh_token = _opaque("rt")
        record = {
            "client_id": client_id,
            "scope": scope,
            "ynab_access_token": ynab_access_token,
            "ynab_refresh_token": ynab_refresh_token,
            "ynab_expires_at": ynab_expires_at,
        }
        await self._kv.put_json(f"oauth:token:{access_token}", record, expiration_ttl=ACCESS_TOKEN_TTL)
        await self._kv.put_json(f"oauth:refresh:{refresh_token}", record)
        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_TTL,
                "refresh_token": refresh_token,
                "scope": scope,
            }
        )

    # -- The one hook the multi-tenant middleware calls --------------------

    async def resolve_token(self, presented: str) -> str:
        """Given whatever token a request presented, return the value that
        should actually be used as the YNAB credential.

        If `presented` is one of this module's own opaque access tokens
        (looked up in KV), returns the underlying YNAB access token —
        transparently refreshing it first if it's within a minute of
        expiring, so a client doesn't need to race the clock. Otherwise
        returns `presented` unchanged: today's behavior, where the presented
        value *is* the caller's own YNAB personal access token.
        """
        record = await self._kv.get_json(f"oauth:token:{presented}")
        if record is None:
            return presented
        if time.time() >= record["ynab_expires_at"] - 60:
            refreshed = await self._refresh_ynab_token(record["ynab_refresh_token"])
            if refreshed is not None:
                ynab_access_token, ynab_refresh_token, ynab_expires_at = refreshed
                record = {**record, "ynab_access_token": ynab_access_token, "ynab_refresh_token": ynab_refresh_token, "ynab_expires_at": ynab_expires_at}
                await self._kv.put_json(f"oauth:token:{presented}", record, expiration_ttl=ACCESS_TOKEN_TTL)
        return record["ynab_access_token"]

    # -- Discovery metadata --------------------------------------------------

    async def authorization_server_metadata(self, _: Request) -> Response:
        issuer = self._settings.oauth_issuer_url
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/oauth/authorize",
                "token_endpoint": f"{issuer}/oauth/token",
                "registration_endpoint": f"{issuer}/oauth/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "scopes_supported": ["read-only"],
            }
        )

    def routes(self) -> list[Route]:
        return [
            Route("/oauth/register", self.register_client, methods=["POST"]),
            Route("/oauth/authorize", self.authorize, methods=["GET"]),
            Route("/oauth/ynab/callback", self.ynab_callback, methods=["GET"]),
            Route("/oauth/token", self.token, methods=["POST"]),
            Route("/.well-known/oauth-authorization-server", self.authorization_server_metadata, methods=["GET"]),
        ]


def build_oauth_proxy(settings: Settings) -> OAuthProxy | None:
    """Returns an OAuthProxy if this deployment has OAuth configured, else
    None — the caller (src/server/http.py) simply skips wiring in the routes
    and token resolution when this returns None, so an unconfigured
    deployment behaves exactly as it did before this module existed."""
    if not (settings.ynab_oauth_client_id and settings.ynab_oauth_client_secret):
        return None
    if not (settings.cloudflare_account_id and settings.cloudflare_kv_namespace_id and settings.cloudflare_kv_api_token):
        raise RuntimeError(
            "YNAB_OAUTH_CLIENT_ID/SECRET are set but CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_KV_NAMESPACE_ID/"
            "CLOUDFLARE_KV_API_TOKEN are not — the OAuth proxy needs somewhere durable to store tokens."
        )
    kv = KVStore(settings.cloudflare_account_id, settings.cloudflare_kv_namespace_id, settings.cloudflare_kv_api_token)
    return OAuthProxy(settings, kv)
