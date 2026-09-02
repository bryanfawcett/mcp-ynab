"""Tests for the streamable-http ASGI app (src/server/http.py)."""

import os

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def http_app(monkeypatch):
    monkeypatch.setenv("YNAB_API_KEY", "test-key")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token")
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
