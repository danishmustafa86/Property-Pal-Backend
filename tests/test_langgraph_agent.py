import pytest

from app.agents.graph import InvestmentAnalystGraph
from app.agents.guardrails import create_confirmation_token, sanitize_update_payload
from app.agents.tools.tools import MacroAnalyst


def test_sanitize_update_payload_drops_unknown_fields():
    payload = {"price": 1000000, "city": "Lahore", "unknown_flag": True}
    sanitized = sanitize_update_payload(payload)
    assert "unknown_flag" not in sanitized
    assert sanitized["price"] == 1000000
    assert sanitized["city"] == "Lahore"


def test_confirmation_token_shape():
    token = create_confirmation_token()
    assert isinstance(token, str)
    assert len(token) == 10


def test_macro_analyst_yoy_and_correlation():
    analyst = MacroAnalyst()
    yoy = analyst.yoy_growth_all()
    assert "median_prices" in yoy
    assert yoy["median_prices"].get("yoy_pct") is not None
    corr = analyst.mortgage_price_correlation()
    assert "correlation" in corr


@pytest.mark.asyncio
async def test_investment_graph_clarifies_vague_query():
    agent = InvestmentAnalystGraph()
    out = await agent.run(
        query="Please give me a full investment analysis report with no city named",
        user={"id": "u1", "role": "user"},
        thread_id="u1:t1",
    )
    assert out.get("structured_analysis")
    assert out["structured_analysis"]["recommendation"] == "Hold"
    assert out["structured_analysis"]["confidence_score"] == 0
    assert (out.get("tool_results") or [{}])[0].get("result", {}).get("status") == "needs_clarification"


@pytest.mark.asyncio
async def test_investment_graph_valid_query_structure(monkeypatch):
    async def fake_tavily(_queries, max_results: int = 4):
        return [{"query": "q", "results": [{"title": "t", "content": "c"}]}]

    monkeypatch.setattr("app.agents.graph.run_tavily_queries", fake_tavily)

    async def fake_boss(self, state):
        from app.agents.investment_models import (
            MANDATORY_DISCLAIMER,
            ForecastChartPoint,
            StructuredAnalysisOutput,
        )

        fc = (state.get("forecast") or {}).get("forecast_chart_data") or []
        pts = [ForecastChartPoint(**x) for x in fc[:3]] if fc else []
        if not pts:
            pts = [ForecastChartPoint(period="2025-08", predicted_price=1.0)]
        structured = StructuredAnalysisOutput(
            recommendation="Hold",
            confidence_score=55,
            forecast_chart_data=pts,
            risk_factors=["Test risk"],
            legal_notes=f"Test legal\n\n{MANDATORY_DISCLAIMER}",
        )

        d = structured.model_dump()
        d["disclaimer"] = MANDATORY_DISCLAIMER
        prior = state.get("last_tool_results") or []
        from langchain_core.messages import AIMessage

        return {
            "structured_analysis": d,
            "messages": [AIMessage(content="## Summary\nHold.")],
            "last_tool_results": prior + [{"name": "investment_boss_synthesis", "result": d}],
        }

    monkeypatch.setattr(InvestmentAnalystGraph, "_boss_node", fake_boss)
    agent = InvestmentAnalystGraph()

    out = await agent.run(
        query="Investment outlook for 5 marla house in DHA Lahore Pakistan",
        user={"id": "u1", "role": "user"},
        thread_id="u1:t2",
    )
    assert out.get("structured_analysis")
    assert out["structured_analysis"]["recommendation"] == "Hold"
    assert out["structured_analysis"]["confidence_score"] == 55
    from app.agents.investment_models import MANDATORY_DISCLAIMER

    assert MANDATORY_DISCLAIMER in out["structured_analysis"].get("legal_notes", "")
