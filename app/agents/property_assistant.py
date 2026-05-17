"""
LangGraph property-search assistant — LLM-powered with tool calling.

Flow:
  user query
      │
      ▼
  [llm_call]  ──tool_call──►  [run_tool]  ──► back to llm_call
      │
   no tool call
      │
      ▼
  [format_response]  ──►  END

The LLM (GPT-4o) decides which tools to call based on intent.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.agents.tools.location_tools import (
    find_houses_near_place,
    find_properties_near_location,
    find_properties_ranked_by_amenities,
    geocode_location,
    get_amenities_near_location,
    search_properties,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

_TOOLS = [
    find_houses_near_place,          # PRIMARY: one-step location+proximity+amenities
    search_properties,               # general filter search (city/budget/beds)
    get_amenities_near_location,     # "what's near X?"
    geocode_location,                # low-level geocoding if needed alone
    find_properties_near_location,   # low-level proximity if needed alone
    find_properties_ranked_by_amenities,  # low-level amenity ranking if needed alone
]

_SYSTEM_PROMPT = """You are PropFinder AI — an expert property search assistant for Pakistan's real estate market.

## Your tools

| Tool | When to use |
|------|-------------|
| **find_houses_near_place** | **PRIMARY TOOL** — any time user mentions a specific place, area, neighbourhood, housing society, road, or landmark. Geocodes + finds + ranks in one call. |
| search_properties | General filters only — city, budget, bedrooms, type. No specific place mentioned. |
| get_amenities_near_location | User asks "what is near X?" (info only, not looking for houses). |
| geocode_location | Only when you need coordinates for a separate purpose. |
| find_properties_near_location | Only when you already have lat/lng from a prior call. |
| find_properties_ranked_by_amenities | Only when you already have lat/lng from a prior call. |

## Decision logic — follow in order

1. User mentions ANY specific place (neighbourhood, society, road, landmark) → call **find_houses_near_place** immediately
   - Pass the place name directly as `location_query`
   - Pass `amenity_types` if user wants hospitals/schools/etc
   - Examples: "near City Housing Samundari Road" → find_houses_near_place(location_query="City Housing Samundari Road Faisalabad")
   - "DHA Phase 5 houses with schools" → find_houses_near_place(location_query="DHA Phase 5 Lahore", amenity_types=["school"])

2. General city/budget/bed search with no specific place → **search_properties**

3. "What is near [place]?" (no house search) → geocode_location + get_amenities_near_location

## Conversation memory — IMPORTANT
You have full memory of this conversation. Always act on it immediately — NEVER ask for more info if you already have enough to search.

Short follow-up handling (call the tool RIGHT AWAY, do not ask questions):
- "yes" / "ok" / "sure" / "haan" / "go ahead" → execute whatever you just offered or described
- "show me" / "find them" / "search" / "go" → call the search tool now using context from previous messages
- "more" / "show more" → repeat last search, limit doubled
- "cheaper" / "lower budget" → re-run last search with max_price halved
- "under X lac" / "under X crore" → re-run last search with that new max_price
- "bigger" / "more beds" / "X beds" → re-run with that bedrooms filter
- "in [area]" / "in [city]" → re-run last search for that new location
- "with garage" / "furnished" / "with parking" → add that filter and re-run
- "what about [city]?" → same last filters in new city

**Golden rule: when the user says something short and ambiguous, look at the last assistant message, extract whatever city/purpose/budget was mentioned, and call the search tool with those values. Do NOT ask the user for information you can infer from context.**

## Search-immediately rule (most important)
If the user message contains BOTH a city AND a purpose (rent/buy) → call search_properties RIGHT NOW without asking anything.
- "find me a house for rent in Faisalabad" → call search_properties(city="Faisalabad", purpose="rent") immediately
- "yes" after you asked about budget → search with no budget filter (return all)
- "yes" after you described what you can find → search now

Never ask for budget or bedrooms as a prerequisite. Search with what you have; the user can refine afterwards.

## Location tool rule (ABSOLUTE)
NEVER say "I couldn't find the location" or "I don't know that area" without FIRST calling geocode_location.
The geocode_location tool handles ALL Pakistani place names, neighbourhoods, housing societies, and roads — even partial names, alternate spellings, or informal names like "City Housing Samundari Road Faisalabad".
Always call the tool. Let the tool report failure; never assume it will fail.

Examples of queries that MUST trigger geocode_location:
- "near City Housing Samundari Road" → geocode_location("City Housing Samundari Road Faisalabad")
- "near DHA Phase 5" → geocode_location("DHA Phase 5")
- "near Jinnah Hospital Karachi" → geocode_location("Jinnah Hospital Karachi")
- "in Bahria Town" → geocode_location("Bahria Town Pakistan")

## Response format

After getting tool results, respond in this exact format:

1. One sentence summary (e.g. "Found 8 houses for rent in Johar Town under 1.5 lac, ranked by nearby hospitals and schools.")
2. Key insight if amenities were searched: which property has the most amenities and why it stands out.
3. End with exactly: RESULTS_JSON:<json_array>

The RESULTS_JSON must be a valid JSON array of property objects from the tool results.
Include distance_from_search_m when available. Include nearby_places and amenity_summary when present.
Include at most 10 properties. Do NOT wrap in markdown code fences.

## CRITICAL — Price conversion (always do this before calling any tool)
Always convert Pakistani price units to full PKR integers:
- 1 lac / lakh / lacs = 100,000 → pass 100000
- 2 lac = 200,000 → pass 200000
- 50k / 50,000 = 50,000 → pass 50000
- 1 crore = 10,000,000 → pass 10000000
- 1.5 crore = 15,000,000 → pass 15000000

NEVER pass 1 meaning "1 lac" — always convert first.
Example: "under 1 lac" → max_price=100000, "under 3 lac" → max_price=300000

## Scope
- Only answer property search questions (rent, buy, location, amenities)
- Refuse investment advice, mortgage questions, market forecasts
- All properties are in Pakistan; prices are in PKR; distances in metres
"""


_KEEP_LAST_N = 10  # max non-system messages to keep in context


def _compact_history(messages: list) -> list:
    """
    Strip large payloads from PREVIOUS turns only, keeping the CURRENT turn intact.

    Current turn = everything after the last HumanMessage.
    These messages must remain in full so the LLM can read tool results and
    write RESULTS_JSON correctly.

    Previous turns:
    - ToolMessage → replaced with "[Tool X found N results]"
    - AIMessage with RESULTS_JSON → blob stripped, prose kept
    - Keep only the last _KEEP_LAST_N non-system messages total

    This prevents TPM limits while giving the LLM full access to current results.
    """
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    other_msgs  = [m for m in messages if not isinstance(m, SystemMessage)]

    # Find the boundary: last HumanMessage index (start of current turn)
    last_human_idx = None
    for i in range(len(other_msgs) - 1, -1, -1):
        if isinstance(other_msgs[i], HumanMessage):
            last_human_idx = i
            break

    compacted: list = []
    for i, m in enumerate(other_msgs[-_KEEP_LAST_N:]):
        # Adjust index relative to the full list
        actual_idx = len(other_msgs) - _KEEP_LAST_N + i
        is_current_turn = last_human_idx is not None and actual_idx >= last_human_idx

        if is_current_turn:
            # Keep current turn messages exactly as-is
            compacted.append(m)
            continue

        # Compact previous-turn messages
        if isinstance(m, ToolMessage):
            raw = str(m.content)
            try:
                data = json.loads(raw)
                count = len(data.get("results", [])) if isinstance(data, dict) else "?"
                summary = f"[Tool '{getattr(m, 'name', '')}' found {count} results]"
            except Exception:
                summary = raw[:200] + ("..." if len(raw) > 200 else "")
            m = ToolMessage(
                content=summary,
                tool_call_id=m.tool_call_id,
                name=getattr(m, "name", ""),
            )
        elif isinstance(m, AIMessage) and isinstance(m.content, str):
            content = m.content
            if "RESULTS_JSON:" in content:
                idx = content.index("RESULTS_JSON:")
                blob = content[idx + len("RESULTS_JSON:"):].strip()
                try:
                    n = len(json.loads(blob)) if blob.startswith("[") else "?"
                except Exception:
                    n = "?"
                content = content[:idx].strip() + f"\n[{n} results shown to user]"
                m = AIMessage(content=content, tool_calls=getattr(m, "tool_calls", []))
        compacted.append(m)

    return system_msgs + compacted


def _parse_agent_output(content: str) -> tuple[str, list[dict]]:
    """Split LLM response into (human_message, property_results_list)."""
    marker = "RESULTS_JSON:"
    if marker not in content:
        return content.strip(), []

    idx = content.index(marker)
    human_part = content[:idx].strip()
    json_part = content[idx + len(marker):].strip()

    # Strip markdown fences if LLM added them anyway
    if json_part.startswith("```"):
        lines = json_part.split("\n")
        json_part = "\n".join(
            l for l in lines
            if not l.strip().startswith("```")
        ).strip()
        if json_part.startswith("json"):
            json_part = json_part[4:].strip()

    try:
        results = json.loads(json_part)
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        if not isinstance(results, list):
            results = []
    except json.JSONDecodeError:
        logger.warning("Could not parse RESULTS_JSON from agent output")
        results = []

    return human_part, results


class PropertyAssistantGraph:
    """LLM-powered property assistant using LangGraph ReAct agent."""

    def __init__(self) -> None:
        api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — assistant will return error responses")

        self._llm = ChatOpenAI(
            model=settings.llm_model or "gpt-4o",
            temperature=settings.llm_temperature,
            api_key=api_key or "missing",
        )
        # MemorySaver persists the full conversation per thread_id in-process.
        # We pass `prompt` as a callable so we can inject the system message AND
        # compact old tool/AI messages before each LLM call — keeping context
        # rich but token count within the TPM limit.
        system_msg = SystemMessage(content=_SYSTEM_PROMPT)

        def _build_prompt(state: dict) -> list:
            compacted = _compact_history(state.get("messages", []))
            return [system_msg] + compacted

        self._memory = MemorySaver()
        self._agent = create_react_agent(
            model=self._llm,
            tools=_TOOLS,
            prompt=_build_prompt,
            checkpointer=self._memory,
        )

    async def run(
        self,
        *,
        query: str,
        thread_id: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        tid = thread_id or str(uuid.uuid4())

        try:
            result = await self._agent.ainvoke(
                {"messages": [HumanMessage(content=query.strip())]},
                config={"configurable": {"thread_id": tid}},
            )
        except Exception as exc:
            logger.exception("Agent run failed: %s", exc)
            return {
                "thread_id": tid,
                "assistant_message": (
                    "Sorry, I had trouble with your request. "
                    "Please try again or use the Search page."
                ),
                "interpreted_filters": {},
                "results": [],
                "amenities_relaxed": False,
                "search_location": None,
            }

        # Extract final AI message (prose only — strip RESULTS_JSON)
        messages = result.get("messages", [])
        final_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage) and m.content),
            None,
        )
        raw_content = final_ai.content if final_ai else ""
        assistant_message, _llm_results = _parse_agent_output(str(raw_content))

        # AUTHORITATIVE results: always come from the actual tool ToolMessages.
        # The LLM often hallucinates fake property data in RESULTS_JSON; using
        # ToolMessages guarantees we return real DB records.
        _RESULT_TOOLS = {
            "find_houses_near_place",
            "find_properties_near_location",
            "find_properties_ranked_by_amenities",
            "search_properties",
        }
        results: list[dict] = []
        search_location: dict | None = None

        for msg in reversed(messages):
            name = getattr(msg, "name", "")
            if isinstance(msg, ToolMessage):
                try:
                    data = json.loads(msg.content)
                except Exception:
                    continue

                # Extract search_location from geocode or combined tool
                if not search_location:
                    if name == "geocode_location" and "lat" in data:
                        search_location = data
                    elif name == "find_houses_near_place":
                        slat = data.get("search_lat")
                        slng = data.get("search_lng")
                        if slat and slng:
                            search_location = {
                                "lat": slat, "lng": slng,
                                "formatted_address": data.get("geocoded_address", ""),
                            }

                # Extract property results
                if not results and name in _RESULT_TOOLS:
                    results = data.get("results") or []
                    if results:
                        pass  # keep iterating only for search_location

            if results and search_location:
                break  # found everything we need

        # LLM results as last resort if no tool results found
        if not results:
            results = _llm_results

        # Attach distance from search location if not already on each result
        if search_location and results:
            from app.agents.tools.location_tools import _haversine_m
            slat = search_location.get("lat")
            slng = search_location.get("lng")
            if slat and slng:
                for r in results:
                    if "distance_from_search_m" not in r and r.get("latitude") and r.get("longitude"):
                        r["distance_from_search_m"] = _haversine_m(slat, slng, r["latitude"], r["longitude"])

        return {
            "thread_id": tid,
            "assistant_message": assistant_message or "Here are the results I found.",
            "interpreted_filters": {},
            "results": results[:limit],
            "amenities_relaxed": False,
            "search_location": search_location,
        }
