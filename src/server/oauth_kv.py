"""Async client for Cloudflare's Workers KV over its REST API.

Used by src/server/oauth.py to durably store OAuth clients, authorization
codes, and tokens. A native KV binding (`env.OAUTH_KV`) is only reachable
from the Worker's own TypeScript code -- a Container is separate compute,
not a Workers isolate, so this container reaches the same KV namespace over
plain HTTPS instead, using an API token scoped to it.
"""

import json
from typing import Any

import httpx

_API_BASE = "https://api.cloudflare.com/client/v4"


class KVError(Exception):
    """A non-2xx response from the Cloudflare KV REST API (other than a
    missing key, which callers see as `None`, not an exception)."""


class KVStore:
    def __init__(self, account_id: str, namespace_id: str, api_token: str, timeout: float = 10.0) -> None:
        self._base = f"{_API_BASE}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}"
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout,
        )

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Returns the parsed JSON value for `key`, or None if it doesn't exist."""
        response = await self._client.get(f"{self._base}/values/{key}")
        if response.status_code == 404:
            return None
        if response.is_error:
            raise KVError(f"GET {key}: HTTP {response.status_code}: {response.text}")
        return response.json()

    async def put_json(self, key: str, value: dict[str, Any], *, expiration_ttl: int | None = None) -> None:
        """Stores `value` as JSON under `key`. `expiration_ttl` (seconds) lets
        Cloudflare expire the key on its own -- used for short-lived
        authorization codes so there's no cleanup job to run."""
        params = {"expiration_ttl": expiration_ttl} if expiration_ttl else None
        response = await self._client.put(
            f"{self._base}/values/{key}",
            params=params,
            content=json.dumps(value),
            headers={"Content-Type": "application/json"},
        )
        if response.is_error:
            raise KVError(f"PUT {key}: HTTP {response.status_code}: {response.text}")

    async def delete(self, key: str) -> None:
        response = await self._client.delete(f"{self._base}/values/{key}")
        if response.is_error:
            raise KVError(f"DELETE {key}: HTTP {response.status_code}: {response.text}")

    async def close(self) -> None:
        await self._client.aclose()
