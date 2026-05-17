from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import MongoModel
from app.schemas.search import SearchFilters


class ChatQueryRequest(MongoModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    thread_id: str | None = None
    confirmation_token: str | None = None


class ChatQueryResponse(MongoModel):
    thread_id: str
    assistant_message: str
    interpreted_filters: SearchFilters | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirmation: dict | None = None
    tool_results: list[dict] = Field(default_factory=list)
    # Geocoded search location — present when user typed a place name
    search_location: dict[str, Any] | None = None


class QueryHistoryRecord(MongoModel):
    id: str
    user_id: str
    query: str
    interpreted_filters: dict
    created_at: datetime
