from src.server import _shared, icons
from src.server._shared import serialize


@_shared.mcp.tool(icons=[icons.USER])
@_shared.handle_errors
async def get_user(exclude_fields: list[str] | None = None) -> str:
    """Get the authenticated user's information.

    Args:
        exclude_fields: Optional list of field names to exclude from the response.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    user = await _shared.cache.get_user()
    return serialize(user, exclude_fields=exclude_fields)
