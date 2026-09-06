"""Tests for src/config.py's Settings, focused on the multi-tenant env vars.

Container platforms often can't express an unset env var and pass an empty
string for a secret that wasn't configured (see worker/src/index.ts's
`this.env.X ?? ""` pass-through) — Settings needs to treat that as unset
rather than erroring (an empty string isn't a valid bool) or treating "" as
a real key/token.
"""

from src.config import Settings


def test_blank_ynab_api_key_is_none():
    settings = Settings(YNAB_API_KEY="", MCP_MULTI_TENANT="true")
    assert settings.ynab_api_key is None


def test_blank_mcp_auth_token_is_none():
    settings = Settings(YNAB_API_KEY="key", MCP_AUTH_TOKEN="")
    assert settings.mcp_auth_token is None


def test_blank_multi_tenant_is_false():
    settings = Settings(YNAB_API_KEY="key", MCP_MULTI_TENANT="")
    assert settings.multi_tenant is False


def test_real_multi_tenant_value_still_parses():
    settings = Settings(YNAB_API_KEY="key", MCP_MULTI_TENANT="true")
    assert settings.multi_tenant is True
