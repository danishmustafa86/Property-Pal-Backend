from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.guardrails import sanitize_update_payload
from app.services.property_service import PropertyService


class GetPropertyInput(BaseModel):
    property_id: str = Field(min_length=4)


class UpdatePropertyInput(BaseModel):
    property_id: str = Field(min_length=4)
    updates: dict[str, Any]


class PublishPropertyInput(BaseModel):
    property_id: str = Field(min_length=4)
    listing_status: str = Field(pattern="^(active|archived)$")


def build_property_tools(user: dict, enable_write_tools: bool = True) -> list:
    service = PropertyService()

    @tool("list_my_properties")
    async def list_my_properties() -> list[dict]:
        """List properties owned by the authenticated user."""
        return await service.list_for_owner(user)

    @tool("get_property_details", args_schema=GetPropertyInput)
    async def get_property_details(**kwargs) -> dict:
        """Get full property details by id."""
        data = GetPropertyInput(**kwargs)
        return await service.get(data.property_id)

    tools: list = [list_my_properties, get_property_details]

    if not enable_write_tools:
        return tools

    @tool("create_property_post")
    async def create_property_post(payload: dict[str, Any]) -> dict:
        """Create a new property listing from a complete payload."""
        from app.schemas.property import PropertyCreate

        model = PropertyCreate(**payload)
        return await service.create(user, model)

    @tool("update_property_post", args_schema=UpdatePropertyInput)
    async def update_property_post(**kwargs) -> dict:
        """Update editable fields of an existing property listing."""
        from app.schemas.property import PropertyUpdate

        data = UpdatePropertyInput(**kwargs)
        safe_updates = sanitize_update_payload(data.updates)
        model = PropertyUpdate(**safe_updates)
        return await service.update(user, data.property_id, model)

    @tool("publish_property_post", args_schema=PublishPropertyInput)
    async def publish_property_post(**kwargs) -> dict:
        """Publish or archive an existing property listing."""
        data = PublishPropertyInput(**kwargs)
        return await service.publish(user, data.property_id, data.listing_status)

    tools.extend([create_property_post, update_property_post, publish_property_post])
    return tools
