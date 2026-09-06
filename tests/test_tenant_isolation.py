"""Verifies the contextvar-backed tenant proxies in src/server/_shared.py
actually isolate concurrent requests from each other.

This is the core correctness property multi-tenant mode depends on: two
requests handled concurrently on the same event loop (as Starlette/uvicorn
do) must never see each other's YNABClient/CacheService, since that would
mean one person's request could read or act on another person's YNAB budget.
"""

import asyncio

import pytest

from src.server import _shared


class _FakeInstance:
    def __init__(self, name: str):
        self.name = name


@pytest.mark.asyncio
async def test_activate_tenant_isolates_concurrent_tasks():
    barrier = asyncio.Barrier(2)

    async def handle_request(name: str):
        tokens = _shared.activate_tenant(_FakeInstance(name), _FakeInstance(name), f"/tmp/{name}.db")
        try:
            # Force both tasks to be "in flight" at once before either reads
            # back _shared.client/_shared.cache, so a shared-global bug (as
            # opposed to a real per-task contextvar) would show up as a race.
            await barrier.wait()
            assert _shared.client.name == name
            assert _shared.cache.name == name
        finally:
            _shared.deactivate_tenant(tokens)

    await asyncio.gather(handle_request("tenant-a"), handle_request("tenant-b"))

    # Once both requests finish, this task's contextvars are back to unset —
    # _shared.client/_shared.cache fall back to the process-wide default,
    # which doesn't have a `.name` attribute.
    with pytest.raises(AttributeError):
        _ = _shared.client.name
