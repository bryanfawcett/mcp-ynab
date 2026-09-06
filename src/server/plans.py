from src.server import _shared, icons
from src.server._shared import serialize, serialize_list


@_shared.mcp.tool(icons=[icons.PLAN])
@_shared.handle_errors
async def list_plans(exclude_fields: list[str] | None = None) -> str:
    """List all plans in the user's YNAB account. Call this first to get plan IDs.

    Args:
        exclude_fields: Optional list of field names to exclude from each plan.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    plans = await _shared.cache.get_plans()
    return serialize_list(plans, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.PLAN])
@_shared.handle_errors
async def get_plan(plan_id: str, exclude_fields: list[str] | None = None) -> str:
    """Get details for a specific plan.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from the response.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    plan = await _shared.cache.get_plan(plan_id)
    return serialize(plan, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.PLAN])
@_shared.handle_errors
async def get_plan_settings(
    plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """Get settings for a plan (date format and currency format).

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from the response.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    plan_settings = await _shared.cache.get_plan_settings(plan_id)
    return serialize(plan_settings, exclude_fields=exclude_fields)
