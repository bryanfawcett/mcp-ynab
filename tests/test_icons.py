"""Every tool needs an icon (see src/server/icons.py) — a tool added without
one is easy to miss by eye across ~50 registrations spread over 10 files, so
this is enforced here instead.
"""

import pytest

from src.server._shared import mcp

# Importing src.server registers every @mcp.tool()/@mcp.resource() definition.
import src.server  # noqa: F401


@pytest.mark.asyncio
async def test_every_tool_has_an_icon():
    tools = await mcp.list_tools()
    missing = [t.name for t in tools if not t.icons]
    assert missing == []


def test_server_has_an_icon():
    assert mcp.icons
