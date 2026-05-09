import json
import logging

from app.agents.parser import QueryParser
from app.agents.query_graph import QueryGraphAgent
from app.repositories.queries import QueryRepository
from app.schemas.common import serialize_mongo_id
from app.schemas.chat import ChatQueryRequest
from app.schemas.search import SearchFilters, SearchRequest
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)


def _format_price(price: int) -> str:
    if price >= 1_00_00_000:
        return f"{price / 1_00_00_000:.1f} Crore"
    if price >= 1_00_000:
        return f"{price / 1_00_000:.1f} Lac"
    if price >= 1000:
        return f"{price / 1000:.0f}K"
    return str(price)


def _format_area(area_payload: dict) -> str:
    if not isinstance(area_payload, dict):
        return ""
    value = area_payload.get("value")
    unit = area_payload.get("unit")
    if value in (None, ""):
        return ""
    if unit:
        return f"{value} {unit}"
    return str(value)


def _build_conversational_message(query: str, filters: dict, results: list[dict]) -> str:
    city = filters.get("city")
    purpose = filters.get("purpose")
    prop_type = filters.get("property_type") or "property"
    min_price = filters.get("min_price")
    max_price = filters.get("max_price")
    rooms = filters.get("rooms")
    min_marlas = filters.get("min_marlas")
    max_marlas = filters.get("max_marlas")

    if not results:
        no_match_parts: list[str] = []
        scope = " ".join(filter(None, [
            f"for {purpose}" if purpose else "",
            f"in {city}" if city else "",
            f"under PKR {_format_price(max_price)}" if max_price else "",
        ])).strip() or "matching your request"

        no_match_parts.append(f"Nothing active {scope} at the moment.")

        tweaks: list[str] = []
        if max_price:
            tweaks.append(f"bump the budget above PKR {_format_price(max_price)}")
        if min_marlas or max_marlas:
            tweaks.append("broaden the size range a bit")
        if rooms:
            tweaks.append("drop the bedroom count by one")
        if city:
            tweaks.append("try a neighbouring area or city")
        if not tweaks:
            tweaks = ["add a city and purpose to the search"]

        no_match_parts.append("You could try: " + ", or ".join(tweaks[:2]) + ".")
        return " ".join(no_match_parts)

    # --- results found ---
    prices = [r.get("price", 0) for r in results if r.get("price")]
    price_range = ""
    if prices:
        lo, hi = min(prices), max(prices)
        price_range = (
            f"PKR {_format_price(lo)}" if lo == hi
            else f"PKR {_format_price(lo)} – {_format_price(hi)}"
        )

    city_label = f" in {city}" if city else ""
    purpose_label = f" for {purpose}" if purpose else ""
    intro = f"Here are {len(results)} active listings{purpose_label}{city_label}"
    if price_range:
        intro += f", ranging from {price_range}"
    intro += "."

    lines: list[str] = [intro, ""]
    for idx, item in enumerate(results[:3], start=1):
        title = item.get("title", "Untitled")
        price = _format_price(item.get("price", 0))
        location = item.get("location") or item.get("city") or ""
        beds = item.get("number_of_bedrooms")
        area = _format_area(item.get("area", {}))

        detail_bits = []
        if location:
            detail_bits.append(location)
        if beds:
            detail_bits.append(f"{beds} bed")
        if area:
            detail_bits.append(area)

        lines.append(f"**{idx}. {title}** — PKR {price}" + (f"  \n{', '.join(detail_bits)}" if detail_bits else ""))

    if len(results) > 3:
        lines.append(f"\n{len(results) - 3} more are in the cards below — let me know if you want to filter further.")
    else:
        lines.append("\nLet me know if you'd like to compare these or narrow down by budget or location.")

    return "\n".join(lines)


def _build_smart_suggestions(query: str, filters: dict, results: list[dict]) -> list[str]:
    city = filters.get("city", "")
    purpose = filters.get("purpose", "buy")
    prop_type = filters.get("property_type", "")

    suggestions: list[str] = []

    if results:
        prices = [r.get("price", 0) for r in results if r.get("price")]
        if prices:
            avg = sum(prices) // len(prices)
            suggestions.append(f"Show options under PKR {_format_price(avg)}")
        if city:
            suggestions.append(f"Best investment areas in {city}")
        if not prop_type or prop_type == "house":
            suggestions.append("Show me apartments instead")
        if purpose == "buy":
            suggestions.append("Show rental options too")
        elif purpose == "rent":
            suggestions.append("What about buying instead?")
        suggestions.append("Compare top 3 options with pros and cons")
    else:
        if city:
            suggestions.append(f"Show all listings in {city}")
        suggestions.append("Houses for sale in Lahore under 1 crore")
        suggestions.append("Apartments for rent in Islamabad")
        suggestions.append("Show properties near schools and hospitals")

    return suggestions[:4]


class ChatService:
    def __init__(self) -> None:
        self.agent = QueryGraphAgent()
        self.query_repo = QueryRepository()
        self.search_service = SearchService()

    @staticmethod
    def _sanitize_filters_for_response(raw: dict | None) -> SearchFilters | None:
        if not raw:
            return None
        try:
            return SearchFilters.model_validate(raw)
        except Exception:
            logger.warning("Could not coerce interpreted_filters for chat response; dropping.")
            return None

    async def query(self, user: dict, payload: ChatQueryRequest) -> dict:
        thread_id = payload.thread_id or f"{user['id']}:default"
        agent_response = await self.agent.run(
            query=payload.query,
            user=user,
            thread_id=thread_id,
            confirmation_token=payload.confirmation_token,
        )
        interpreted_filters = self._extract_interpreted_filters(agent_response.get("tool_results", []))
        structured = agent_response.get("structured_analysis")
        if structured and not interpreted_filters:
            try:
                interpreted_filters = QueryParser().parse(payload.query).model_dump(exclude_none=True)
            except Exception:
                interpreted_filters = {}
        results = self._extract_search_items(agent_response.get("tool_results", []), limit=payload.limit)

        used_fallback = any(r.get("name") == "fallback_parser" for r in agent_response.get("tool_results", []))

        if structured:
            used_fallback = False

        if not results and interpreted_filters and not structured:
            try:
                search_kwargs = {
                    k: v
                    for k, v in interpreted_filters.items()
                    if k in SearchRequest.model_fields and k != "page_size" and v is not None
                }
                search_req = SearchRequest(page_size=payload.limit, **search_kwargs)
                search_result = await self.search_service.search(search_req)
                results = search_result.get("items", [])[:payload.limit]
            except Exception as exc:
                logger.warning("Chat search fallback failed (continuing without listings): %s", exc)

        history_payload = json.loads(json.dumps(interpreted_filters or {}, default=str))
        try:
            await self.query_repo.create_query_record(
                user_id=str(user["id"]),
                query=payload.query,
                interpreted_filters=history_payload,
            )
        except Exception as exc:
            logger.warning("Skipping query history write (chat still succeeds): %s", exc)

        if structured:
            assistant_msg = agent_response.get("assistant_message", "") or _build_conversational_message(
                payload.query, interpreted_filters, results
            )
        elif used_fallback or "keyword-based" in agent_response.get("assistant_message", "").lower():
            assistant_msg = _build_conversational_message(payload.query, interpreted_filters, results)
        else:
            assistant_msg = agent_response.get("assistant_message", "")
            if not assistant_msg or assistant_msg.strip() == "":
                assistant_msg = _build_conversational_message(payload.query, interpreted_filters, results)

        safe_filters = self._sanitize_filters_for_response(interpreted_filters)

        return {
            "thread_id": thread_id,
            "assistant_message": assistant_msg,
            "interpreted_filters": safe_filters,
            "results": results,
            "suggestions": _build_smart_suggestions(payload.query, interpreted_filters, results),
            "pending_confirmation": agent_response.get("pending_confirmation"),
            "tool_results": agent_response.get("tool_results", []),
            "structured_analysis": structured,
        }

    async def history(self, user: dict) -> list[dict]:
        rows = await self.query_repo.get_history(user["id"])
        return [serialize_mongo_id(r) for r in rows]

    @staticmethod
    def _extract_search_items(tool_results: list[dict], limit: int) -> list[dict]:
        for result in reversed(tool_results):
            payload = result.get("result")
            if result.get("name") == "search_properties" and isinstance(payload, dict):
                items = payload.get("items", [])
                if isinstance(items, list):
                    return items[:limit]
        return []

    @staticmethod
    def _extract_interpreted_filters(tool_results: list[dict]) -> dict:
        for result in reversed(tool_results):
            payload = result.get("result")
            if result.get("name") == "search_properties" and isinstance(payload, dict):
                return payload.get("request", payload.get("filters", {})) if isinstance(payload, dict) else {}
            if result.get("name") == "fallback_parser" and isinstance(payload, dict):
                return payload.get("interpreted_filters", {})
        return {}
