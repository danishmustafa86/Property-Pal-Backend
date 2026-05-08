"""LangGraph workflow: Validator → Researcher → Forecaster → Boss (investment synthesis)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any, Literal, TypedDict

import pandas as pd
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from sklearn.linear_model import LinearRegression

from app.agents.investment_models import MANDATORY_DISCLAIMER, ForecastChartPoint, StructuredAnalysisOutput
from app.agents.parser import QueryParser
from app.agents.tools.tools import MacroAnalyst, build_investment_tavily_queries, run_tavily_queries
from app.core.config import settings
from app.schemas.search import SearchRequest
from app.services.search_service import SearchService

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None

logger = logging.getLogger(__name__)

LOCATION_HINTS = [
    "dha",
    "bahria",
    "gulberg",
    "johar",
    "model town",
    "clifton",
    "defence",
    "defense",
    "blue area",
    "faisal town",
    "gulistan",
    "scheme",
]


def _coerce_null_llm_content(messages: list) -> list:
    from langchain_core.messages import AIMessage as _AIM

    out: list = []
    for msg in messages:
        if isinstance(msg, _AIM):
            tool_calls = getattr(msg, "tool_calls", None) or []
            raw = getattr(msg, "content", None)
            if raw is None or (isinstance(raw, str) and not raw.strip() and tool_calls):
                payload = msg.model_dump()
                payload["content"] = " " if tool_calls else ""
                out.append(_AIM.model_validate(payload))
                continue
        out.append(msg)
    return out


class InvestmentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    user: dict[str, Any]
    raw_query: str
    location_label: str
    country: str
    validation_ok: bool
    clarification_message: str
    macro_report: dict[str, Any]
    tavily_results: list[Any]
    listing_micro: dict[str, Any]
    forecast: dict[str, Any]
    structured_analysis: dict[str, Any] | None
    last_tool_results: list[dict[str, Any]]


def _infer_country(query: str, city: str | None) -> str:
    lower = query.lower()
    mapping = [
        ("pakistan", "Pakistan"),
        ("uae", "United Arab Emirates"),
        ("dubai", "United Arab Emirates"),
        ("abu dhabi", "United Arab Emirates"),
        ("india", "India"),
        ("bangladesh", "Bangladesh"),
        ("saudi", "Saudi Arabia"),
        ("qatar", "Qatar"),
        ("kuwait", "Kuwait"),
        ("oman", "Oman"),
        ("uk", "United Kingdom"),
        ("united kingdom", "United Kingdom"),
        ("usa", "United States"),
        ("united states", "United States"),
    ]
    for needle, label in mapping:
        if needle in lower:
            return label
    if city:
        return "Pakistan"
    return "Pakistan"


def _has_location_hint(query: str, parsed_city: str | None) -> bool:
    """Require a recognizable city or named area — generic keywords alone are not enough."""
    if parsed_city:
        return True
    lower = query.lower()
    for h in LOCATION_HINTS:
        if h in lower:
            return True
    for c in QueryParser.CITY_KEYWORDS:
        if c in lower:
            return True
    return False


class InvestmentAnalystGraph:
    """Four-node professional workflow for real-estate investment analysis."""

    def __init__(self) -> None:
        self.parser = QueryParser()
        self.checkpointer = InMemorySaver()
        self._graph = self._compile()

    def _build_llms(self) -> list:
        if ChatOpenAI is None:
            return []
        keys: list[str] = []
        if settings.openai_api_key:
            keys.append(settings.openai_api_key)
        if settings.openai_api_key_fallback and settings.openai_api_key_fallback not in keys:
            keys.append(settings.openai_api_key_fallback)
        llms: list = []
        for key in keys:
            kwargs: dict[str, Any] = {
                "model": settings.llm_model,
                "api_key": key,
                "temperature": settings.llm_temperature,
                "max_tokens": min(settings.llm_max_tokens, 2048),
            }
            if settings.llm_base_url:
                kwargs["base_url"] = settings.llm_base_url
            llms.append(ChatOpenAI(**kwargs))
        return llms

    async def _validator_node(self, state: dict[str, Any]) -> dict[str, Any]:
        query = (state.get("raw_query") or "").strip()
        if len(query) < 8:
            return {
                "validation_ok": False,
                "clarification_message": (
                    "Your request is too short to analyze safely. "
                    "Please name a city or area and country (for example: "
                    "'Investment outlook for 5 Marla in DHA Lahore, Pakistan')."
                ),
                "location_label": "",
                "country": "",
            }

        parsed = self.parser.parse(query)
        city = parsed.city
        if not _has_location_hint(query, city):
            return {
                "validation_ok": False,
                "clarification_message": (
                    "I need a clearer location to run macro and live web research. "
                    "Which city or district (and country) should I use—for example "
                    "Faisalabad, Lahore DHA, or Karachi Clifton?"
                ),
                "location_label": "",
                "country": "",
            }

        location = city or (keyword or "")[:80] or query[:80]
        country = _infer_country(query, city)
        return {
            "validation_ok": True,
            "clarification_message": "",
            "location_label": location.strip(),
            "country": country,
        }

    def _route_validation(self, state: dict[str, Any]) -> Literal["research", "clarify"]:
        return "research" if state.get("validation_ok") else "clarify"

    async def _clarify_node(self, state: dict[str, Any]) -> dict[str, Any]:
        msg = state.get("clarification_message") or "Please specify location and country for analysis."
        structured = {
            "recommendation": "Hold",
            "confidence_score": 0,
            "forecast_chart_data": [],
            "risk_factors": ["Analysis was not run because the location context was ambiguous or missing."],
            "legal_notes": MANDATORY_DISCLAIMER,
            "disclaimer": MANDATORY_DISCLAIMER,
        }
        tool_row = {
            "name": "investment_validator",
            "result": {"status": "needs_clarification", "message": msg},
        }
        return {
            "messages": [AIMessage(content=msg)],
            "structured_analysis": structured,
            "last_tool_results": [tool_row],
        }

    async def _researcher_node(self, state: dict[str, Any]) -> dict[str, Any]:
        location = state.get("location_label") or ""
        country = state.get("country") or "Pakistan"
        loop = asyncio.get_running_loop()

        def macro_job() -> dict[str, Any]:
            return MacroAnalyst().full_report()

        macro_task = loop.run_in_executor(None, macro_job)
        queries = build_investment_tavily_queries(location, country)
        tavily_task = run_tavily_queries(queries, max_results=4)

        listing_task = self._fetch_listing_micro(location)

        macro_report, tavily_results, listing_micro = await asyncio.gather(
            macro_task, tavily_task, listing_task
        )

        tool_rows = [
            {"name": "macro_analyst_local", "result": macro_report},
            {"name": "tavily_live_research", "result": tavily_results},
        ]
        if listing_micro:
            tool_rows.append({"name": "listing_market_micro", "result": listing_micro})

        return {
            "macro_report": macro_report,
            "tavily_results": tavily_results,
            "listing_micro": listing_micro or {},
            "last_tool_results": tool_rows,
        }

    async def _fetch_listing_micro(self, location: str, parsed_city: str | None = None) -> dict[str, Any] | None:
        city = parsed_city or None
        if not city and location:
            lower = location.lower()
            for c in QueryParser.CITY_KEYWORDS:
                if c in lower:
                    city = c.title()
                    break
        if not city:
            return None
        try:
            svc = SearchService()
            req = SearchRequest(page_size=5, city=city, purpose="buy")
            return await svc.search(req)
        except Exception as exc:
            logger.warning("Listing micro snapshot failed: %s", exc)
            return {"error": str(exc), "items": []}

    def _forecaster_node(self, state: dict[str, Any]) -> dict[str, Any]:
        series = state.get("macro_report", {}).get("price_series") or []
        horizon = max(6, min(12, int(settings.investment_forecast_horizon_months or 12)))
        default_out: dict[str, Any] = {
            "forecast_chart_data": [],
            "model_note": "insufficient_history",
            "r2": None,
        }
        if len(series) < 3:
            return {"forecast": default_out}

        df = pd.DataFrame(series)
        x = df[["index"]].values
        y = df["price"].astype(float).values
        model = LinearRegression()
        model.fit(x, y)
        r2 = float(model.score(x, y)) if len(x) > 1 else None
        last_idx = float(df["index"].iloc[-1])
        last_period = str(df["period"].iloc[-1])
        try:
            last_ts = pd.to_datetime(last_period)
        except Exception:
            last_ts = pd.Timestamp.utcnow()

        chart: list[dict[str, Any]] = []
        for h in range(1, horizon + 1):
            xi = [[last_idx + h]]
            pred = float(model.predict(xi)[0])
            ts = last_ts + pd.DateOffset(months=h)
            chart.append({"period": str(ts.date())[:7], "predicted_price": max(pred, 0.0)})

        note = "linear_trend_on_local_median_series"
        return {"forecast": {"forecast_chart_data": chart, "model_note": note, "r2": r2}}

    async def _boss_node(self, state: dict[str, Any]) -> dict[str, Any]:
        forecast = state.get("forecast") or {}
        chart_points = forecast.get("forecast_chart_data") or []
        macro = state.get("macro_report") or {}
        tavily = state.get("tavily_results") or []
        listing = state.get("listing_micro") or {}
        location = state.get("location_label") or ""
        country = state.get("country") or ""

        payload = {
            "user_query": state.get("raw_query"),
            "location": location,
            "country": country,
            "macro": macro,
            "web_research": tavily,
            "active_listings_sample": listing,
            "forecaster_output": forecast,
        }
        system = (
            "You are a senior real-estate investment analyst. "
            "Synthesize macro CSV metrics, Tavily web snippets, and the numeric forecast. "
            "Return structured JSON fields only via the provided schema. "
            "Use the forecaster's chart points exactly for `forecast_chart_data` when they are non-empty "
            "(copy period and predicted_price). "
            "Recommendation must be exactly one of: Buy, Hold, Sell. "
            "confidence_score is an integer 0-100. "
            "risk_factors: 3-6 concise bullets. "
            "legal_notes: summarize tax/regulatory themes from web research; stay non-definitive. "
            "Do not invent specific laws or portal prices not hinted in the inputs."
        )
        human = f"Context JSON:\n{json.dumps(payload, default=str)[:24000]}"

        llms = self._build_llms()
        structured: StructuredAnalysisOutput | None = None
        if llms:
            for idx, llm in enumerate(llms):
                try:
                    structured_llm = llm.with_structured_output(StructuredAnalysisOutput)
                    structured = await structured_llm.ainvoke(
                        _coerce_null_llm_content([SystemMessage(content=system), HumanMessage(content=human)])
                    )
                    if idx > 0:
                        logger.warning("Boss synthesis succeeded via fallback LLM key.")
                    break
                except Exception as exc:
                    logger.warning("Boss LLM failed on key #%s: %s", idx + 1, exc)

        if structured is None:
            structured = self._fallback_structured(chart_points, macro, tavily)

        if chart_points:
            structured.forecast_chart_data = [ForecastChartPoint(**row) for row in chart_points[:12]]

        legal = structured.legal_notes.strip()
        if MANDATORY_DISCLAIMER not in legal:
            structured.legal_notes = f"{legal}\n\n{MANDATORY_DISCLAIMER}".strip()

        analysis_dict = structured.model_dump()
        analysis_dict["disclaimer"] = MANDATORY_DISCLAIMER

        narrative = self._render_executive_summary(structured, location, country)
        tool_row = {"name": "investment_boss_synthesis", "result": analysis_dict}

        prior = state.get("last_tool_results") or []
        return {
            "structured_analysis": analysis_dict,
            "messages": [AIMessage(content=narrative)],
            "last_tool_results": prior + [tool_row],
        }

    @staticmethod
    def _fallback_structured(
        chart_points: list[dict[str, Any]],
        macro: dict[str, Any],
        tavily: list[dict[str, Any]],
    ) -> StructuredAnalysisOutput:
        risks = [
            "LLM synthesis unavailable; using conservative rule-based output.",
            "Verify all figures against primary sources and licensed advisers.",
        ]
        if not tavily or all(not r.get("results") for r in tavily):
            risks.append("Live web research returned little or no data; geopolitical and tax context may be incomplete.")
        yoy = (macro.get("yoy") or {}).get("median_prices", {})
        if yoy.get("yoy_pct") is not None and float(yoy["yoy_pct"]) > 5:
            rec: Literal["Buy", "Hold", "Sell"] = "Buy"
            conf = 42
        elif yoy.get("yoy_pct") is not None and float(yoy["yoy_pct"]) < -2:
            rec = "Sell"
            conf = 38
        else:
            rec = "Hold"
            conf = 45
        fc = [ForecastChartPoint(**row) for row in chart_points[:12]]
        return StructuredAnalysisOutput(
            recommendation=rec,
            confidence_score=conf,
            forecast_chart_data=fc,
            risk_factors=risks,
            legal_notes=MANDATORY_DISCLAIMER,
        )

    @staticmethod
    def _render_executive_summary(out: StructuredAnalysisOutput, location: str, country: str) -> str:
        lines = [
            f"## Investment brief — {location}, {country}",
            "",
            f"**Recommendation:** {out.recommendation}  ",
            f"**Confidence:** {out.confidence_score}%",
            "",
            "### Key risks",
        ]
        for r in out.risk_factors[:6]:
            lines.append(f"- {r}")
        lines.extend(["", "### Legal / regulatory notes", out.legal_notes])
        return "\n".join(lines)

    def _compile(self):
        g = StateGraph(InvestmentState)
        g.add_node("validator", self._validator_node)
        g.add_node("clarify", self._clarify_node)
        g.add_node("researcher", self._researcher_node)
        g.add_node("forecaster", self._forecaster_node)
        g.add_node("boss", self._boss_node)

        g.add_edge(START, "validator")
        g.add_conditional_edges(
            "validator",
            self._route_validation,
            {"research": "researcher", "clarify": "clarify"},
        )
        g.add_edge("clarify", END)
        g.add_edge("researcher", "forecaster")
        g.add_edge("forecaster", "boss")
        g.add_edge("boss", END)
        return g.compile(checkpointer=self.checkpointer)

    async def run(
        self,
        *,
        query: str,
        user: dict[str, Any],
        thread_id: str,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        _ = confirmation_token  # legacy signature; investment graph ignores write-confirm flow
        initial = {
            "messages": [HumanMessage(content=query)],
            "thread_id": thread_id,
            "user": user,
            "raw_query": query,
            "location_label": "",
            "country": "",
            "validation_ok": False,
            "clarification_message": "",
            "macro_report": {},
            "tavily_results": [],
            "listing_micro": {},
            "forecast": {},
            "structured_analysis": None,
            "last_tool_results": [],
        }
        result = await self._graph.ainvoke(
            initial,
            config={"configurable": {"thread_id": thread_id}},
        )

        assistant_message = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                assistant_message = (str(msg.content) if msg.content is not None else "").strip()
                break

        return {
            "thread_id": thread_id,
            "assistant_message": assistant_message,
            "summary": "",
            "pending_confirmation": None,
            "tool_results": result.get("last_tool_results", []),
            "structured_analysis": result.get("structured_analysis"),
        }
