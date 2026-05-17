"""AI Assistant chat — LangGraph property search only."""

import logging

from app.agents.property_assistant import PropertyAssistantGraph
from app.schemas.chat import ChatQueryRequest
from app.schemas.search import SearchFilters

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self) -> None:
        self._agent = PropertyAssistantGraph()

    async def query(self, user: dict, payload: ChatQueryRequest) -> dict:
        thread_id = payload.thread_id or f"{user['id']}:default"
        try:
            result = await self._agent.run(
                query=payload.query,
                thread_id=thread_id,
                limit=payload.limit,
            )
        except Exception as exc:
            logger.exception("Assistant run failed: %s", exc)
            return {
                "thread_id": thread_id,
                "assistant_message": (
                    "Sorry, I had trouble searching listings. Please try again or use the Search page."
                ),
                "interpreted_filters": None,
                "results": [],
                "pending_confirmation": None,
                "tool_results": [],
            }

        raw_filters = result.get("interpreted_filters") or {}
        safe_filters = None
        try:
            safe_filters = SearchFilters.model_validate(raw_filters)
        except Exception:
            logger.warning("Could not validate interpreted_filters")

        return {
            "thread_id": result["thread_id"],
            "assistant_message": result.get("assistant_message", ""),
            "interpreted_filters": safe_filters,
            "results": result.get("results") or [],
            "pending_confirmation": None,
            "search_location": result.get("search_location"),
            "tool_results": [
                {
                    "name": "search_properties",
                    "result": {
                        "filters": raw_filters,
                        "items": result.get("results") or [],
                        "amenities_relaxed": result.get("amenities_relaxed", False),
                    },
                }
            ],
        }

    async def history(self, user: dict) -> list[dict]:
        return []
