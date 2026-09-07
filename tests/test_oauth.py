import base64
import hashlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src.config import Settings
from src.server.oauth import OAuthProxy, _pkce_matches, build_oauth_proxy


class FakeKVStore:
    """In-memory double for KVStore — same async get_json/put_json/delete
    surface, no network calls."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    async def get_json(self, key: str):
        return self._data.get(key)

    async def put_json(self, key: str, value: dict, *, expiration_ttl: int | None = None):
        self._data[key] = value

    async def delete(self, key: str):
        self._data.pop(key, None)

    async def close(self):
        pass


class LaggingKVStore(FakeKVStore):
    """Simulates Cloudflare KV's eventual consistency (see oauth_kv.py's
    docstring and KV_READ_RETRY_ATTEMPTS in oauth.py): a key written via
    put_json returns None from get_json for `misses_before_visible` reads
    before it actually becomes visible, exactly like a read hitting an
    edge location the write hasn't propagated to yet."""

    def __init__(self, misses_before_visible: int) -> None:
        super().__init__()
        self._misses_before_visible = misses_before_visible
        self._miss_counts: dict[str, int] = {}

    async def get_json(self, key: str):
        if key in self._data and self._miss_counts.get(key, 0) < self._misses_before_visible:
            self._miss_counts[key] = self._miss_counts.get(key, 0) + 1
            return None
        return await super().get_json(key)


@pytest.fixture(autouse=True)
def _fast_kv_retries(monkeypatch):
    """OAuthProxy retries a KV miss with real sleeps (KV_READ_RETRY_* in
    oauth.py) to ride out Cloudflare KV's eventual-consistency window in
    production. Tests -- including ones exercising a genuine miss, like an
    unknown client or an already-used code -- shouldn't have to actually
    wait through that backoff."""
    monkeypatch.setattr("src.server.oauth.asyncio.sleep", AsyncMock())


def _pkce_pair():
    verifier = "a" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _ynab_transport(access_token="ynab-at-1", refresh_token="ynab-rt-1"):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth/token"
        return httpx.Response(200, json={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 7200,
            "refresh_token": refresh_token,
        })

    return httpx.MockTransport(handler)


def _make_proxy(transport=None, kv=None) -> tuple[OAuthProxy, FakeKVStore]:
    settings = Settings(
        MCP_MULTI_TENANT=True,
        YNAB_OAUTH_CLIENT_ID="test-client",
        YNAB_OAUTH_CLIENT_SECRET="test-secret",
        CLOUDFLARE_ACCOUNT_ID="acct",
        CLOUDFLARE_KV_NAMESPACE_ID="ns",
        CLOUDFLARE_KV_API_TOKEN="tok",
    )
    kv = kv if kv is not None else FakeKVStore()
    http_client = httpx.AsyncClient(transport=transport or _ynab_transport())
    return OAuthProxy(settings, kv, http_client=http_client), kv


def test_pkce_matches():
    verifier, challenge = _pkce_pair()
    assert _pkce_matches(verifier, challenge, "S256")
    assert not _pkce_matches("wrong-verifier", challenge, "S256")
    assert not _pkce_matches(verifier, challenge, "plain")


def test_build_oauth_proxy_returns_none_when_unconfigured():
    settings = Settings(MCP_MULTI_TENANT=True)
    assert build_oauth_proxy(settings) is None


def test_build_oauth_proxy_requires_kv_config():
    settings = Settings(MCP_MULTI_TENANT=True, YNAB_OAUTH_CLIENT_ID="x", YNAB_OAUTH_CLIENT_SECRET="y")
    with pytest.raises(RuntimeError, match="CLOUDFLARE"):
        build_oauth_proxy(settings)


@pytest.mark.asyncio
async def test_resolve_token_passes_through_unknown_tokens():
    proxy, _ = _make_proxy()
    # A raw YNAB personal access token — not one of ours — is returned as-is.
    assert await proxy.resolve_token("ynab-personal-access-token") == "ynab-personal-access-token"


@pytest.mark.asyncio
async def test_full_authorization_code_flow():
    proxy, kv = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    # 1. Dynamic client registration.
    reg = client.post("/oauth/register", json={"redirect_uris": ["https://client.example/cb"]})
    assert reg.status_code == 201
    client_id = reg.json()["client_id"]

    # 2. /authorize redirects to YNAB with our session id as `state`.
    verifier, challenge = _pkce_pair()
    resp = client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "client-state-123",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    ynab_redirect = httpx.URL(resp.headers["location"])
    assert ynab_redirect.host == "app.ynab.com"
    session_id = ynab_redirect.params["state"]

    # 3. YNAB "redirects back" to our callback with a code + our session id.
    resp = client.get("/oauth/ynab/callback", params={"code": "ynab-code-1", "state": session_id}, follow_redirects=False)
    assert resp.status_code == 302
    client_redirect = httpx.URL(resp.headers["location"])
    assert str(client_redirect).startswith("https://client.example/cb")
    assert client_redirect.params["state"] == "client-state-123"
    our_code = client_redirect.params["code"]

    # 4. The MCP client exchanges our code (+ its PKCE verifier) for tokens.
    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": our_code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["token_type"] == "bearer"
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # The code is single-use.
    resp = client.post(
        "/oauth/token",
        data={"grant_type": "authorization_code", "code": our_code, "redirect_uri": "https://client.example/cb", "code_verifier": verifier},
    )
    assert resp.status_code == 400

    # 5. resolve_token maps our opaque access token to the real YNAB token.
    assert await proxy.resolve_token(access_token) == "ynab-at-1"

    # 6. Refreshing rotates both tokens and still resolves correctly.
    resp = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": refresh_token})
    assert resp.status_code == 200
    new_access_token = resp.json()["access_token"]
    assert new_access_token != access_token
    assert await proxy.resolve_token(new_access_token) == "ynab-at-1"

    await kv.close()


def test_metadata_advertises_both_read_write_and_read_only_scopes():
    # Regression test: scopes_supported previously listed only "read-only",
    # so a spec-compliant client had no way to offer a caller full access --
    # every consent screen built from this document could only ever show
    # "read-only", with no write option to select even though the proxy
    # itself already supports granting full access (see authorize() below).
    proxy, _ = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    assert set(resp.json()["scopes_supported"]) == {"read-write", "read-only"}


@pytest.mark.asyncio
async def test_authorize_requests_read_only_scope_from_ynab_when_asked():
    proxy, _ = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    reg = client.post("/oauth/register", json={"redirect_uris": ["https://client.example/cb"]})
    client_id = reg.json()["client_id"]
    _, challenge = _pkce_pair()

    resp = client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "read-only",
        },
        follow_redirects=False,
    )
    ynab_redirect = httpx.URL(resp.headers["location"])
    assert ynab_redirect.params["scope"] == "read-only"


@pytest.mark.asyncio
async def test_authorize_requests_full_access_from_ynab_by_default():
    # No scope, or "read-write" -- either way, YNAB gets no `scope` param at
    # all, which is how its own /oauth/authorize grants full read-write
    # access (it has no explicit "read-write" scope value of its own).
    proxy, _ = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    for scope_param in ({}, {"scope": "read-write"}):
        reg = client.post("/oauth/register", json={"redirect_uris": ["https://client.example/cb"]})
        client_id = reg.json()["client_id"]
        _, challenge = _pkce_pair()

        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://client.example/cb",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                **scope_param,
            },
            follow_redirects=False,
        )
        ynab_redirect = httpx.URL(resp.headers["location"])
        assert "scope" not in ynab_redirect.params


@pytest.mark.asyncio
async def test_ynab_callback_retries_through_kv_propagation_lag():
    # Regression test for the "expired or unknown authorization session"
    # error a real user hit: authorize() writes the session to Cloudflare
    # KV, then redirects through YNAB and back to ynab_callback() -- a round
    # trip that can complete before the write has propagated to whatever KV
    # edge location serves the callback's read. The session is really
    # there; it just isn't visible yet. A couple of misses should still
    # succeed via the retry.
    proxy, _ = _make_proxy(kv=LaggingKVStore(misses_before_visible=3))
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    reg = client.post("/oauth/register", json={"redirect_uris": ["https://client.example/cb"]})
    client_id = reg.json()["client_id"]
    _, challenge = _pkce_pair()

    resp = client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    session_id = httpx.URL(resp.headers["location"]).params["state"]

    resp = client.get("/oauth/ynab/callback", params={"code": "ynab-code-1", "state": session_id}, follow_redirects=False)
    assert resp.status_code == 302
    assert "code" in httpx.URL(resp.headers["location"]).params


@pytest.mark.asyncio
async def test_ynab_callback_reports_expired_session_when_genuinely_missing():
    proxy, _ = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    resp = client.get("/oauth/ynab/callback", params={"code": "ynab-code-1", "state": "nonexistent-session"})
    assert resp.status_code == 400
    assert resp.json()["error_description"] == "expired or unknown authorization session"


@pytest.mark.asyncio
async def test_token_exchange_retries_through_kv_propagation_lag():
    # Same lag, one hop later: ynab_callback() writes the code, and an MCP
    # client can call /oauth/token to exchange it before that write has
    # propagated.
    proxy, _ = _make_proxy(kv=LaggingKVStore(misses_before_visible=3))
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    reg = client.post("/oauth/register", json={"redirect_uris": ["https://client.example/cb"]})
    client_id = reg.json()["client_id"]
    verifier, challenge = _pkce_pair()

    resp = client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    session_id = httpx.URL(resp.headers["location"]).params["state"]
    resp = client.get("/oauth/ynab/callback", params={"code": "ynab-code-1", "state": session_id}, follow_redirects=False)
    our_code = httpx.URL(resp.headers["location"]).params["code"]

    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": our_code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": verifier,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_authorize_rejects_unknown_client():
    proxy, _ = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    resp = client.get(
        "/oauth/authorize",
        params={
            "client_id": "nonexistent",
            "redirect_uri": "https://client.example/cb",
            "code_challenge": "x",
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_token_exchange_rejects_bad_pkce_verifier():
    proxy, kv = _make_proxy()
    app = Starlette(routes=proxy.routes())
    client = TestClient(app)

    reg = client.post("/oauth/register", json={"redirect_uris": ["https://client.example/cb"]})
    client_id = reg.json()["client_id"]
    _, challenge = _pkce_pair()

    resp = client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "https://client.example/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    session_id = httpx.URL(resp.headers["location"]).params["state"]
    resp = client.get("/oauth/ynab/callback", params={"code": "ynab-code-1", "state": session_id}, follow_redirects=False)
    our_code = httpx.URL(resp.headers["location"]).params["code"]

    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": our_code,
            "redirect_uri": "https://client.example/cb",
            "code_verifier": "wrong-verifier-entirely-different-value",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_grant"
