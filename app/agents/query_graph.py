"""Agent entrypoint: smart intent router → property search or investment analysis."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.graph import InvestmentAnalystGraph
from app.agents.parser import QueryParser
from app.schemas.search import SearchRequest
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

# Investment-specific patterns — checked first to avoid false search matches
_INVESTMENT_PATTERNS = [
    r"\binvest(?:ment|ing|ed)?\b",
    r"\b(?:roi|return on investment|capital gain|yield)\b",
    r"\b(?:price forecast|price trend|price analysis|price prediction|market outlook|market analysis)\b",
    r"\bshould i (?:buy|invest|sell)\b",
    r"\b(?:appreciation|depreciation)\b.{0,20}\b(?:property|real estate|market)\b",
    r"\b(?:forecast|outlook)\b.{0,20}\b(?:property|real estate|market|price)\b",
    r"\bmarket (?:trends?|analysis|outlook|report)\b",
    r"\bprice (?:trend|forecast|prediction|analysis)\b",
    r"\blong.?term\b.{0,30}\b(?:property|real estate|buy|invest)\b",
]

# Property search / listing patterns
_SEARCH_PATTERNS = [
    r"\b(?:show|find|get|give|display|list)\b.{0,50}\b(?:house|houses|flat|flats|apartment|apartments|property|properties|plot|plots|shop|office)\b",
    r"\b(?:house|houses|flat|flats|apartment|apartments|property|properties|plot|plots|shop)\b.{0,40}\b(?:for rent|for sale|to rent|to buy|available)\b",
    r"\b(?:looking for|want to|need a|searching for)\b.{0,50}\b(?:house|flat|apartment|property|plot)\b",
    r"\b(?:find me|show me)\b",
    r"\b(?:house|houses|flat|flats|apartment|apartments|property|properties|plot|plots)\b.{0,30}\b(?:in|at|near|around)\b",
    r"\b(?:rent|buy|purchase)\b.{0,30}\b(?:house|flat|apartment|property|plot)\b",
    r"\b(?:homes?|flats?|apartments?|houses?)\b.{0,30}\b(?:for (?:rent|sale)|in|under|below|available)\b",
    r"\bavailable\b.{0,30}\b(?:house|flat|apartment|property|plot)\b",
]

_KNOWN_CITIES = QueryParser.CITY_KEYWORDS + [
    "dha", "bahria", "gulberg", "clifton", "johar", "defence", "defense",
    "model town", "gulshan", "blue area", "faisal town", "scheme", "pechs",
]


def _classify_intent(query: str) -> str:
    """Return 'search' or 'investment'. Investment check runs first."""
    lower = query.lower()

    for pattern in _INVESTMENT_PATTERNS:
        if re.search(pattern, lower):
            return "investment"

    for pattern in _SEARCH_PATTERNS:
        if re.search(pattern, lower):
            return "search"

    # Heuristic: recognised city/area + purpose word or plain price → likely a search
    has_city = any(c in lower for c in _KNOWN_CITIES)
    has_purpose = any(p in lower for p in ("rent", "buy", "sale", "purchase"))
    has_price = bool(re.search(r"\b\d{4,}\b", lower))

    if has_city and (has_purpose or has_price):
        return "search"

    return "investment"


class QueryGraphAgent:
    """Routes queries to direct property search or the investment analyst workflow."""

    def __init__(self) -> None:
        self._analyst = InvestmentAnalystGraph()
        self._parser = QueryParser()
        self._search_service = SearchService()

    async def run(
        self,
        *,
        query: str,
        user: dict[str, Any],
        thread_id: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        intent = _classify_intent(query)
        logger.info("Query intent=%s: %.80s", intent, query)

        if intent == "search":
            return await self._run_property_search(query, thread_id)

        return await self._analyst.run(
            query=query,
            user=user,
            thread_id=thread_id,
            confirmation_token=confirmation_token,
        )

    async def _run_property_search(self, query: str, thread_id: str) -> dict[str, Any]:
        """Parse the query for filters and fetch matching listings from the database."""
        parsed = self._parser.parse(query)
        filters = parsed.model_dump(exclude_none=True)

        try:
            search_kwargs = {k: v for k, v in filters.items() if k in SearchRequest.model_fields}
            search_req = SearchRequest(page_size=10, **search_kwargs)
            result = await self._search_service.search(search_req)
            tool_results = [{
                "name": "search_properties",
                "result": {
                    **result,
                    "request": filters,
                    "filters": filters,
                },
            }]
        except Exception as exc:
            logger.warning("Direct property search failed: %s", exc)
            tool_results = [{"name": "fallback_parser", "result": {"interpreted_filters": filters}}]

        return {
            "thread_id": thread_id,
            "assistant_message": "",
            "summary": "",
            "pending_confirmation": None,
            "tool_results": tool_results,
            "structured_analysis": None,
        }
