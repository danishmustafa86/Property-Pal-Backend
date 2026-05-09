"""Agent entrypoint: smart intent router → help / property search / investment analysis."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.graph import InvestmentAnalystGraph
from app.agents.parser import QueryParser
from app.core.config import settings
from app.schemas.search import SearchRequest
from app.services.search_service import SearchService

try:
    from langchain_openai import ChatOpenAI as _ChatOpenAI
    from langchain_core.messages import HumanMessage as _HM, SystemMessage as _SM
except Exception:  # pragma: no cover
    _ChatOpenAI = None  # type: ignore[assignment,misc]
    _HM = _SM = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Help / greeting intent (checked first) ──────────────────────────────────
_HELP_PATTERNS = [
    r"^(?:hi|hello|hey|salam|salaam|assalam|assalamualaikum)[\s!.?]*$",
    r"\bhow\s+can\s+(?:you|i)\s+(?:help|assist)\b",
    r"\bwhat\s+can\s+you\s+(?:do|help|provide|offer)\b",
    r"\bwhat\s+(?:are|do)\s+you\s+(?:capable|able|offering)\b",
    r"\bwho\s+are\s+you\b",
    r"\bintroduce\s+yourself\b",
    r"\bwhat\s+(?:services?|features?|capabilities?|functions?)\s+(?:do\s+you|can\s+you|you)\b",
    r"^(?:help|assist)\s+me[\s?!.]*$",
    r"^how\s+(?:can\s+you|do\s+you)\s+help[\s?!.]*$",
    r"\bwhat\s+(?:can|do)\s+(?:i|we)\s+(?:ask|query|search)\b",
]

# ── Investment / advisory intent (checked before search) ────────────────────
_INVESTMENT_PATTERNS = [
    r"\binvest(?:ment|ing|ed)?\b",
    r"\b(?:roi|return on investment|capital gain|yield)\b",
    r"\b(?:price forecast|price trend|price analysis|price prediction|market outlook|market analysis)\b",
    r"\bshould\b.{0,30}\b(?:buy|invest|sell|purchase)\b",   # fixed: words allowed in between
    r"\b(?:appreciation|depreciation)\b.{0,20}\b(?:property|real estate|market)\b",
    r"\b(?:forecast|outlook)\b.{0,20}\b(?:property|real estate|market|price)\b",
    r"\bmarket\s+(?:trends?|analysis|outlook|report|situation|condition|overview)\b",
    r"\bprice\s+(?:trend|forecast|prediction|analysis|decline|drop|rise)\b",
    r"\blong.?term\b.{0,30}\b(?:property|real estate|buy|invest)\b",
    r"\b(?:property|real estate|housing)\s+market\b",
    r"\bflood\s+(?:risk|zone|prone|area|issue|impact)\b",
    r"\b(?:is it|is there)\b.{0,30}\b(?:good|safe|risky|problem|issue|risk)\b.{0,30}\b(?:property|area|buy|invest)\b",
    r"\btell\s+me\s+(?:about|more).{0,40}\b(?:market|area|locality|zone|neighborhood)\b",
    r"\b(?:issues?|problems?|concerns?|risks?)\b.{0,30}\b(?:property|area|location|locality|zone)\b",
    r"\b(?:worth|good\s+time|right\s+time)\b.{0,30}\b(?:buy|invest|purchase)\b",
    r"\b(?:pros?\s+and\s+cons?|advantages?|disadvantages?)\b.{0,30}\b(?:buy|property|area|location)\b",
]

# ── Plain property search intent ─────────────────────────────────────────────
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

_HELP_RESPONSE = (
    "Sure, happy to help! I'm a real estate advisor for Pakistan's property market. "
    "You can ask me to find properties — like *'show 5 marla houses in DHA Lahore under 2 crore'* "
    "— or get my honest take on an area: *'should I buy in Bahria Town Rawalpindi right now?'* "
    "or *'what's the flood situation near Ravi River affecting Shahdra Town prices?'*\n\n"
    "I pull from live web research, macro data (inflation, mortgage rates, price trends), "
    "and active listings in the database to give you a grounded answer. "
    "What would you like to know?"
)


def _classify_intent(query: str) -> str:
    """Return 'help', 'search', or 'investment'. Help and investment are checked before search."""
    lower = query.lower().strip()

    for pattern in _HELP_PATTERNS:
        if re.search(pattern, lower):
            return "help"

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

        if intent == "help":
            return {
                "thread_id": thread_id,
                "assistant_message": _HELP_RESPONSE,
                "summary": "",
                "pending_confirmation": None,
                "tool_results": [],
                "structured_analysis": None,
            }

        if intent == "search":
            return await self._run_property_search(query, thread_id)

        return await self._analyst.run(
            query=query,
            user=user,
            thread_id=thread_id,
            confirmation_token=confirmation_token,
        )

    async def _run_property_search(self, query: str, thread_id: str) -> dict[str, Any]:
        """Parse query, fetch matching listings, then let the LLM write a natural response."""
        parsed = self._parser.parse(query)
        filters = parsed.model_dump(exclude_none=True)
        items: list[dict[str, Any]] = []

        try:
            search_kwargs = {k: v for k, v in filters.items() if k in SearchRequest.model_fields}
            search_req = SearchRequest(page_size=10, **search_kwargs)
            result = await self._search_service.search(search_req)
            items = result.get("items", [])
            tool_results = [{
                "name": "search_properties",
                "result": {**result, "request": filters, "filters": filters},
            }]
        except Exception as exc:
            logger.warning("Direct property search failed: %s", exc)
            tool_results = [{"name": "fallback_parser", "result": {"interpreted_filters": filters}}]

        assistant_message = await self._llm_search_narrative(query, filters, items)

        return {
            "thread_id": thread_id,
            "assistant_message": assistant_message,
            "summary": "",
            "pending_confirmation": None,
            "tool_results": tool_results,
            "structured_analysis": None,
        }

    async def _llm_search_narrative(
        self, query: str, filters: dict[str, Any], items: list[dict[str, Any]]
    ) -> str:
        """Ask the LLM to turn raw search results into a natural conversational reply."""
        if _ChatOpenAI is None or not settings.openai_api_key:
            return ""

        def _fmt(p: int) -> str:
            if p >= 1_00_00_000:
                return f"PKR {p / 1_00_00_000:.1f} Crore"
            if p >= 1_00_000:
                return f"PKR {p / 1_00_000:.0f} Lac"
            return f"PKR {p:,}"

        summaries: list[str] = []
        for r in items[:7]:
            bits: list[str] = [r.get("title", "Untitled"), _fmt(r.get("price", 0))]
            loc = r.get("location") or r.get("city") or ""
            beds = r.get("number_of_bedrooms")
            area = r.get("area") or {}
            area_str = f"{area.get('value')} {area.get('unit', 'marla')}" if area.get("value") else ""
            if loc:
                bits.append(loc)
            if beds:
                bits.append(f"{beds} bed")
            if area_str:
                bits.append(area_str)
            summaries.append(" | ".join(bits))

        listings_block = (
            "\n".join(f"• {s}" for s in summaries)
            if summaries
            else "No listings matched the search criteria."
        )
        filter_ctx = ", ".join(
            f"{k}={v}" for k, v in filters.items()
            if k in ("city", "purpose", "property_type", "max_price", "min_marlas", "max_marlas", "rooms")
            and v is not None
        )

        system = (
            "You are a friendly, knowledgeable Pakistani real estate advisor having a chat. "
            "Given search results, write a natural 2-4 sentence response that: "
            "directly acknowledges what the person is looking for, "
            "summarises what was found (count + price range), "
            "mentions anything noteworthy (price outliers, interesting location pattern), "
            "and optionally offers to narrow things down. "
            "No bullet lists, no section headers, no 'I found X matching listing(s)' template phrasing. "
            "If nothing matched, explain naturally and suggest a practical alternative. "
            "Sound like a trusted friend who knows property — warm, specific, honest."
        )
        human = (
            f"User asked: {query}\n"
            f"Filters: {filter_ctx or 'none'}\n"
            f"Results ({len(items)} total):\n{listings_block}"
        )

        try:
            kwargs: dict[str, Any] = {
                "model": settings.llm_model,
                "api_key": settings.openai_api_key,
                "temperature": 0.45,
                "max_tokens": 200,
            }
            if settings.llm_base_url:
                kwargs["base_url"] = settings.llm_base_url
            llm = _ChatOpenAI(**kwargs)
            resp = await llm.ainvoke([_SM(content=system), _HM(content=human)])
            return (resp.content or "").strip()
        except Exception as exc:
            logger.warning("LLM search narrative failed (falling back to template): %s", exc)
            return ""
