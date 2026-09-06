from src.server import _shared, icons
from src.server._shared import serialize_list


@_shared.mcp.tool(icons=[icons.MONEY_MOVEMENT])
@_shared.handle_errors
async def list_money_movements(
    plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """List all money movements in a plan.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each movement.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    movements = await _shared.cache.get_money_movements(plan_id)
    return serialize_list(movements, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.MONEY_MOVEMENT])
@_shared.handle_errors
async def get_money_movements_for_month(
    month: str, plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """Get all money movements for a specific month.

    Args:
        month: Month in YYYY-MM-DD format (first of month) or 'current'
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each movement.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    movements = await _shared.cache.get_money_movements_for_month(month, plan_id)
    return serialize_list(movements, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.MONEY_MOVEMENT])
@_shared.handle_errors
async def list_money_movement_groups(
    plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """List all money movement groups in a plan.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each group.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    groups = await _shared.cache.get_money_movement_groups(plan_id)
    return serialize_list(groups, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.MONEY_MOVEMENT])
@_shared.handle_errors
async def get_money_movement_groups_for_month(
    month: str, plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """Get all money movement groups for a specific month.

    Args:
        month: Month in YYYY-MM-DD format (first of month) or 'current'
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each group.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    groups = await _shared.cache.get_money_movement_groups_for_month(month, plan_id)
    return serialize_list(groups, exclude_fields=exclude_fields)
