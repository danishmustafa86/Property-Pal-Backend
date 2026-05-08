from __future__ import annotations

from uuid import uuid4

from app.schemas.property import PropertyUpdate

WRITE_TOOL_NAMES = {"create_property_post", "update_property_post", "publish_property_post"}
ALLOWED_UPDATE_FIELDS = set(PropertyUpdate.model_fields.keys())


def is_write_tool_name(tool_name: str) -> bool:
    return tool_name in WRITE_TOOL_NAMES


def has_write_tool_calls(tool_calls: list[dict]) -> bool:
    return any(is_write_tool_name(tc.get("name", "")) for tc in tool_calls)


def sanitize_update_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key in ALLOWED_UPDATE_FIELDS}


def create_confirmation_token() -> str:
    return uuid4().hex[:10]
