import sys
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_db_path() -> str:
    """Platform-appropriate default cache DB path."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "ynab-mcp-server"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "ynab-mcp-server"
    else:
        base = Path.home() / ".local" / "share" / "ynab-mcp-server"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "cache.db")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required for stdio mode and single-tenant HTTP deployments (one server,
    # one YNAB account). Unused — and may be left unset — when multi_tenant is
    # true, since each caller supplies their own YNAB token per request instead.
    ynab_api_key: str | None = Field(default=None, alias="YNAB_API_KEY")
    cache_db_path: str = Field(default_factory=_default_db_path)
    http_timeout: float = 30.0

    # Shared secret required on the Authorization header for the streamable-http
    # transport (src/server/http.py) in single-tenant mode. Unused by the stdio
    # transport, and unused (each caller's own YNAB token is the credential
    # instead) when multi_tenant is true.
    mcp_auth_token: str | None = Field(default=None, alias="MCP_AUTH_TOKEN")

    # When true, src/server/http.py treats the bearer token/query token on each
    # request as that caller's own YNAB personal access token rather than a
    # shared secret gating one YNAB_API_KEY — so a single deployment can serve
    # many people, each seeing only their own budget. See README.md's "Remote
    # deployment" section.
    multi_tenant: bool = Field(default=False, alias="MCP_MULTI_TENANT")

    # OAuth proxy (src/server/oauth.py), layered on top of multi-tenant mode:
    # lets a caller "Sign in with YNAB" instead of pasting a personal access
    # token. Unset means the OAuth routes/token resolution are simply not
    # wired in -- the existing PAT flow is entirely unaffected either way.
    ynab_oauth_client_id: str | None = Field(default=None, alias="YNAB_OAUTH_CLIENT_ID")
    ynab_oauth_client_secret: str | None = Field(default=None, alias="YNAB_OAUTH_CLIENT_SECRET")
    # Public base URL this deployment is reachable at, for building the
    # redirect_uri YNAB sends the user back to and the issuer in the
    # discovery metadata. Not auto-detected from the request, since the
    # Worker forwards requests to the container over a private network
    # address, not the public hostname.
    oauth_issuer_url: str = Field(default="https://ynab.nyuchi.com", alias="OAUTH_ISSUER_URL")
    # Durable storage for authorization codes/tokens/registered clients (see
    # oauth_kv.py) -- the container's own disk is wiped on every idle-sleep,
    # so this can't live there. A Cloudflare KV namespace, reached over its
    # REST API rather than as a native binding, since a Container is separate
    # compute from the Worker and can't use `env.OAUTH_KV` directly.
    cloudflare_account_id: str | None = Field(default=None, alias="CLOUDFLARE_ACCOUNT_ID")
    cloudflare_kv_namespace_id: str | None = Field(default=None, alias="CLOUDFLARE_KV_NAMESPACE_ID")
    cloudflare_kv_api_token: str | None = Field(default=None, alias="CLOUDFLARE_KV_API_TOKEN")

    # TTL for non-delta endpoints (seconds)
    ttl_budgets: int = 300
    ttl_scheduled_transactions: int = 300
    ttl_month_detail: int = 120
    ttl_single_entity: int = 60

    # Delta sync
    delta_min_interval: int = 30

    # Retry
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0

    # Container platforms (e.g. Cloudflare's `envVars`) often can't express an
    # unset env var and pass an empty string for a secret that wasn't
    # configured instead — treat that the same as unset rather than letting
    # pydantic reject "" as an invalid bool, or treating "" as a real key/token.
    @field_validator(
        "ynab_api_key",
        "mcp_auth_token",
        "ynab_oauth_client_id",
        "ynab_oauth_client_secret",
        "cloudflare_account_id",
        "cloudflare_kv_namespace_id",
        "cloudflare_kv_api_token",
        mode="before",
    )
    @classmethod
    def _blank_string_to_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("multi_tenant", mode="before")
    @classmethod
    def _blank_string_to_false(cls, v: object) -> object:
        return False if v == "" else v
