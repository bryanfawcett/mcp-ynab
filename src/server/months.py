from src.server import _shared, icons
from src.server._shared import serialize, serialize_list


@_shared.mcp.tool(icons=[icons.MONTH])
@_shared.handle_errors
async def list_months(
    plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """List all plan months.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each month.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    months = await _shared.cache.get_months(plan_id)
    return serialize_list(months, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.MONTH])
@_shared.handle_errors
async def get_month(
    month: str, plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """Get detailed plan month summary including all categories. Use 'current' for the current month.

    Args:
        month: Month in YYYY-MM-DD format (first of month) or 'current'
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from the response.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    m = await _shared.cache.get_month(month, plan_id)
    return serialize(m, exclude_fields=exclude_fields)
