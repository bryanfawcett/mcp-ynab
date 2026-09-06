from src.server import _shared, icons
from src.server._shared import serialize, serialize_list


@_shared.mcp.tool(icons=[icons.PAYEE_LOCATION])
@_shared.handle_errors
async def list_payee_locations(
    plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """List all payee locations in a plan.

    Args:
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each location.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    locations = await _shared.cache.get_payee_locations(plan_id)
    return serialize_list(locations, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.PAYEE_LOCATION])
@_shared.handle_errors
async def get_payee_location(
    payee_location_id: str,
    plan_id: str,
    exclude_fields: list[str] | None = None,
) -> str:
    """Get a single payee location.

    Args:
        payee_location_id: The payee location ID
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from the response.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    location = await _shared.cache.get_payee_location(payee_location_id, plan_id)
    return serialize(location, exclude_fields=exclude_fields)


@_shared.mcp.tool(icons=[icons.PAYEE_LOCATION])
@_shared.handle_errors
async def get_payee_locations_by_payee(
    payee_id: str, plan_id: str, exclude_fields: list[str] | None = None
) -> str:
    """Get all locations for a specific payee.

    Args:
        payee_id: The payee ID
        plan_id: The plan ID (use list_plans to find available IDs)
        exclude_fields: Optional list of field names to exclude from each location.
            If omitted, the model's default exclude list is used (see FIELDS.md).
            Pass [] to return all fields. Pass a custom list to override the default.
    """
    locations = await _shared.cache.get_payee_locations_by_payee(payee_id, plan_id)
    return serialize_list(locations, exclude_fields=exclude_fields)
