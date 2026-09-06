"""Tests for the streamable-http ASGI app (src/server/http.py)."""

import os

import pytest
from starlette.testclient import TestClient


def _init_request(**overrides):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    body.update(overrides)
    return body


@pytest.fixture
def http_app(monkeypatch):
    monkeypatch.setenv("YNAB_API_KEY", "test-key")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token")
    from src.server import http as http_module

    return http_module.create_app()


@pytest.fixture
def multi_tenant_app(monkeypatch, tmp_path):
    monkeypatch.delenv("YNAB_API_KEY", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MCP_MULTI_TENANT", "true")
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.db"))
    from src.server import http as http_module

    return http_module.create_app()


def test_health_does_not_require_auth(http_app):
    with TestClient(http_app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_mcp_endpoint_rejects_missing_token(http_app):
    with TestClient(http_app) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401


def test_mcp_endpoint_rejects_wrong_token(http_app):
    with TestClient(http_app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert response.status_code == 401


def test_mcp_endpoint_accepts_token_as_query_param(http_app):
    with TestClient(http_app) as client:
        response = client.post(
            "/mcp?token=test-token",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert response.status_code == 200


def test_mcp_endpoint_rejects_wrong_token_as_query_param(http_app):
    with TestClient(http_app) as client:
        response = client.post(
            "/mcp?token=wrong-token",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
    assert response.status_code == 401


def test_mcp_endpoint_accepts_correct_token(http_app):
    with TestClient(http_app) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            headers={
                "Authorization": "Bearer test-token",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200


def test_create_app_requires_auth_token(monkeypatch):
    monkeypatch.setenv("YNAB_API_KEY", "test-key")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    from src.server import http as http_module

    with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN"):
        http_module.create_app()


# ── Multi-tenant mode ─────────────────────────────────────────


def test_multi_tenant_app_does_not_require_mcp_auth_token(multi_tenant_app):
    # create_app() succeeding at all (the fixture) is the assertion: unlike
    # single-tenant mode, no MCP_AUTH_TOKEN/YNAB_API_KEY is configured here.
    assert multi_tenant_app is not None


def test_multi_tenant_rejects_missing_token(multi_tenant_app):
    with TestClient(multi_tenant_app) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401


def test_multi_tenant_accepts_any_nonempty_token(multi_tenant_app):
    # Multi-tenant mode has no shared secret to check the token against — it's
    # forwarded to YNAB as-is on the first real API call, and a bad one fails
    # there. A bare `initialize` never reaches YNAB, so any nonempty token
    # gets past this layer.
    with TestClient(multi_tenant_app) as client:
        response = client.post(
            "/mcp",
            json=_init_request(),
            headers={
                "Authorization": "Bearer someones-real-ynab-token",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200


def test_multi_tenant_accepts_token_as_query_param(multi_tenant_app):
    with TestClient(multi_tenant_app) as client:
        response = client.post(
            "/mcp?token=someones-real-ynab-token",
            json=_init_request(),
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_tenant_registry_isolates_by_token(tmp_path):
    from src.config import Settings
    from src.server.http import TenantRegistry

    settings = Settings(YNAB_API_KEY="unused", MCP_MULTI_TENANT=True)
    registry = TenantRegistry(settings, tmp_path)

    client_a, cache_a, path_a = await registry.get_or_create("token-a")
    client_a_again, cache_a_again, path_a_again = await registry.get_or_create("token-a")
    client_b, cache_b, path_b = await registry.get_or_create("token-b")

    # Same token -> the exact same instances (and db file) reused, not rebuilt.
    assert client_a is client_a_again
    assert cache_a is cache_a_again
    assert path_a == path_a_again

    # Different token -> fully separate instances and cache file.
    assert client_a is not client_b
    assert cache_a is not cache_b
    assert path_a != path_b

    await client_a.close()
    await client_b.close()


@pytest.mark.asyncio
async def test_tenant_registry_evicts_oldest_beyond_cap(tmp_path, monkeypatch):
    from src.config import Settings
    from src.server import http as http_module

    monkeypatch.setattr(http_module, "MAX_TENANTS", 2)
    settings = Settings(YNAB_API_KEY="unused", MCP_MULTI_TENANT=True)
    registry = http_module.TenantRegistry(settings, tmp_path)

    client_1, _, _ = await registry.get_or_create("token-1")
    await registry.get_or_create("token-2")
    await registry.get_or_create("token-3")  # pushes registry over MAX_TENANTS=2

    assert len(registry._entries) == 2
    # token-1 was the oldest and should have been evicted (and its client closed).
    assert registry._tenant_id("token-1") not in registry._entries
    assert client_1._client.is_closed
