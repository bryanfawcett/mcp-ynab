"""Tests for the MCP Apps dashboard UI resource (src/server/dashboard.py)."""

import pytest

from src.server._shared import mcp
from src.server.dashboard import DASHBOARD_URI

# Importing src.server registers every @mcp.tool()/@mcp.resource() definition.
import src.server  # noqa: F401


@pytest.mark.asyncio
async def test_dashboard_resource_is_registered():
    resources = await mcp.list_resources()
    dashboard = next((r for r in resources if str(r.uri) == DASHBOARD_URI), None)
    assert dashboard is not None
    assert dashboard.mime_type == "text/html;profile=mcp-app"
    assert dashboard.meta["ui"]["csp"]["resourceDomains"] == [
        "https://esm.sh",
        "https://cdn.jsdelivr.net",
    ]


@pytest.mark.asyncio
async def test_dashboard_resource_content():
    result = await mcp.read_resource(DASHBOARD_URI)
    content = result[0].content
    assert "<title>Budget Dashboard</title>" in content
    assert "@modelcontextprotocol/ext-apps" in content
    assert "chart.js" in content
    assert "ontoolresult" in content


@pytest.mark.asyncio
async def test_get_monthly_report_links_to_dashboard():
    tools = await mcp.list_tools()
    tool = next(t for t in tools if t.name == "get_monthly_report")
    assert tool.meta["ui"]["resourceUri"] == DASHBOARD_URI
    assert tool.meta["ui/resourceUri"] == DASHBOARD_URI
