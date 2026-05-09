"""Structured outputs for the investment analyst (boss / API layer)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ForecastChartPoint(BaseModel):
    period: str = Field(description="Month label, e.g. 2026-06 or M+6")
    predicted_price: float = Field(description="Projected median or typical price in local currency units")


class StructuredAnalysisOutput(BaseModel):
    recommendation: Literal["Buy", "Hold", "Sell"] = Field(
        description="Investment stance given macro, micro, and forecast context."
    )
    confidence_score: int = Field(ge=0, le=100, description="Confidence in the recommendation (0-100).")
    summary: str = Field(
        default="",
        description=(
            "2-4 sentence narrative that directly addresses the user's specific concerns "
            "(e.g. flood risk, affordability, locality outlook). Natural, advisory tone."
        ),
    )
    forecast_chart_data: list[ForecastChartPoint] = Field(
        default_factory=list,
        description="6-12 month forward price trend points; align with forecaster when provided.",
    )
    risk_factors: list[str] = Field(default_factory=list, description="Key risks and caveats.")
    legal_notes: str = Field(
        default="",
        description="Tax/regulatory notes from web research; must not replace licensed advice.",
    )


MANDATORY_DISCLAIMER = (
    "Disclaimer: This is an AI-generated analysis based on historical and web data. "
    "Consult a legal professional before financial commitments."
)
