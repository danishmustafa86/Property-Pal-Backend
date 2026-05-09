"""Investment research utilities: local macro CSVs (FRED-style) and Tavily live search."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

# Optional LangChain Tavily tool (requires langchain-community + TAVILY_API_KEY)
try:
    from langchain_community.tools.tavily_search import TavilySearchResults
except Exception:  # pragma: no cover
    TavilySearchResults = None  # type: ignore[misc, assignment]


def _backend_data_dir() -> Path:
    base = Path(settings.data_dir) if settings.data_dir else Path(__file__).resolve().parents[3] / "data"
    return base


def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.copy()
    date_candidates = ["date", "observation_date", "period", "time", "month"]
    date_col = next((c for c in date_candidates if c in out.columns), None)
    if date_col is None:
        # first column if parseable as date
        first = out.columns[0]
        try:
            out["_dt"] = pd.to_datetime(out[first], errors="coerce")
            out = out.dropna(subset=["_dt"])
            out = out.rename(columns={first: "date"})
        except Exception:
            return None
    else:
        out["_dt"] = pd.to_datetime(out[date_col], errors="coerce")
        out = out.dropna(subset=["_dt"])
        out["date"] = out["_dt"]
    out = out.sort_values("date")
    return out


def _value_column(df: pd.DataFrame, preferred: list[str]) -> str | None:
    for name in preferred:
        if name in df.columns:
            return name
    numeric_cols = [c for c in df.columns if c not in ("date", "_dt") and pd.api.types.is_numeric_dtype(df[c])]
    return numeric_cols[0] if numeric_cols else None


class MacroAnalyst:
    """Loads local macro CSVs and computes YoY metrics and mortgage–price correlation."""

    FILE_MAP = {
        "mortgage_rates": "mortgage_rates.csv",
        "housing_supply": "housing_supply.csv",
        "inflation": "inflation.csv",
        "median_prices": "median_prices.csv",
    }

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or _backend_data_dir()

    def _read_csv(self, filename: str) -> pd.DataFrame | None:
        path = self.data_dir / filename
        if not path.is_file():
            logger.warning("Macro CSV missing: %s", path)
            return None
        try:
            return pd.read_csv(path)
        except Exception as exc:
            logger.warning("Failed reading %s: %s", path, exc)
            return None

    def load_mortgage_rates(self) -> pd.DataFrame | None:
        return _normalize_date_column(self._read_csv(self.FILE_MAP["mortgage_rates"]))

    def load_housing_supply(self) -> pd.DataFrame | None:
        return _normalize_date_column(self._read_csv(self.FILE_MAP["housing_supply"]))

    def load_inflation(self) -> pd.DataFrame | None:
        return _normalize_date_column(self._read_csv(self.FILE_MAP["inflation"]))

    def load_median_prices(self) -> pd.DataFrame | None:
        return _normalize_date_column(self._read_csv(self.FILE_MAP["median_prices"]))

    @staticmethod
    def _yoy_for_frame(df: pd.DataFrame | None, value_candidates: list[str], label: str) -> dict[str, Any]:
        if df is None or len(df) < 2:
            return {"metric": label, "yoy_pct": None, "note": "insufficient_rows"}
        vcol = _value_column(df, value_candidates)
        if not vcol:
            return {"metric": label, "yoy_pct": None, "note": "no_value_column"}
        series = df.sort_values("date").copy()
        series[vcol] = pd.to_numeric(series[vcol], errors="coerce")
        series = series.dropna(subset=[vcol])
        if len(series) < 2:
            return {"metric": label, "yoy_pct": None, "note": "non_numeric_values"}
        last_date = series["date"].iloc[-1]
        cutoff = last_date - pd.DateOffset(years=1)
        past = series[series["date"] <= cutoff]
        if past.empty:
            # fallback: compare last vs first if span < 1y
            if (series["date"].iloc[-1] - series["date"].iloc[0]).days < 300:
                return {"metric": label, "yoy_pct": None, "note": "series_shorter_than_one_year"}
            old = series.iloc[0][vcol]
        else:
            old = past.iloc[-1][vcol]
        new = series.iloc[-1][vcol]
        if old in (0, None) or pd.isna(old):
            return {"metric": label, "yoy_pct": None, "note": "invalid_baseline"}
        yoy = float((new - old) / abs(old) * 100.0)
        return {
            "metric": label,
            "yoy_pct": round(yoy, 3),
            "latest": float(new),
            "baseline": float(old),
            "latest_date": str(series["date"].iloc[-1].date()),
        }

    def yoy_growth_all(self) -> dict[str, Any]:
        return {
            "mortgage_rates": self._yoy_for_frame(
                self.load_mortgage_rates(), ["mortgage_rate", "rate", "value"], "mortgage_rates"
            ),
            "housing_supply": self._yoy_for_frame(
                self.load_housing_supply(), ["supply_index", "supply", "value"], "housing_supply"
            ),
            "inflation": self._yoy_for_frame(self.load_inflation(), ["inflation_rate", "cpi", "value"], "inflation"),
            "median_prices": self._yoy_for_frame(
                self.load_median_prices(), ["median_price", "price", "value"], "median_prices"
            ),
        }

    def mortgage_price_correlation(self) -> dict[str, Any]:
        m = self.load_mortgage_rates()
        p = self.load_median_prices()
        if m is None or p is None or m.empty or p.empty:
            return {"correlation": None, "note": "missing_mortgage_or_price_series"}
        mv = _value_column(m, ["mortgage_rate", "rate", "value"])
        pv = _value_column(p, ["median_price", "price", "value"])
        if not mv or not pv:
            return {"correlation": None, "note": "value_columns_not_found"}
        left = m[["date", mv]].rename(columns={mv: "mortgage"})
        right = p[["date", pv]].rename(columns={pv: "price"})
        merged = pd.merge_asof(
            left.sort_values("date"),
            right.sort_values("date"),
            on="date",
            direction="nearest",
            tolerance=pd.Timedelta("45 days"),
        )
        merged = merged.dropna(subset=["mortgage", "price"])
        if len(merged) < 3:
            merged = pd.merge(left, right, on="date", how="inner").dropna(subset=["mortgage", "price"])
        if len(merged) < 3:
            return {"correlation": None, "note": "insufficient_aligned_points", "points": len(merged)}
        corr = float(merged["mortgage"].corr(merged["price"]))
        return {"correlation": round(corr, 4), "points": len(merged), "method": "aligned_mortgage_vs_median_price"}

    def price_series_for_forecast(self) -> list[dict[str, Any]]:
        p = self.load_median_prices()
        if p is None or p.empty:
            return []
        pv = _value_column(p, ["median_price", "price", "value"])
        if not pv:
            return []
        s = p.sort_values("date").copy()
        s[pv] = pd.to_numeric(s[pv], errors="coerce")
        s = s.dropna(subset=[pv])
        rows: list[dict[str, Any]] = []
        for i, (_, row) in enumerate(s.iterrows()):
            rows.append({"index": float(i), "period": str(row["date"].date()), "price": float(row[pv])})
        return rows

    def full_report(self) -> dict[str, Any]:
        return {
            "yoy": self.yoy_growth_all(),
            "mortgage_price_correlation": self.mortgage_price_correlation(),
            "price_series": self.price_series_for_forecast(),
        }


def _tavily_api_key() -> str | None:
    return (settings.tavily_api_key or os.environ.get("TAVILY_API_KEY") or "").strip() or None


def build_tavily_search_tool(max_results: int = 5) -> Any:
    """LangChain TavilySearchResults tool (uses ``TAVILY_API_KEY`` / settings)."""
    if TavilySearchResults is None:
        logger.warning("langchain_community not installed; TavilySearchResults unavailable.")
        return None
    if not _tavily_api_key():
        return None
    key = _tavily_api_key()
    if key and not os.environ.get("TAVILY_API_KEY"):
        os.environ["TAVILY_API_KEY"] = key
    return TavilySearchResults(max_results=max_results)


async def run_tavily_queries(queries: list[str], max_results: int = 4) -> list[dict[str, Any]]:
    """Parallel Tavily searches via ``tavily`` async client (same API as TavilySearchResults)."""
    key = _tavily_api_key()
    if not key:
        return [{"query": q, "error": "tavily_unconfigured", "results": []} for q in queries]

    try:
        from tavily import AsyncTavilyClient
    except ImportError:
        tool = build_tavily_search_tool(max_results=max_results)
        if tool is None:
            return [{"query": q, "error": "tavily_client_unavailable", "results": []} for q in queries]

        async def one_lc(q: str) -> dict[str, Any]:
            try:
                raw = await tool.ainvoke({"query": q})
                body = raw[:8000] if isinstance(raw, str) else raw
                return {"query": q, "results": body}
            except Exception as exc:
                logger.warning("Tavily search failed: %s", exc)
                return {"query": q, "error": str(exc), "results": []}

        return await asyncio.gather(*[one_lc(q) for q in queries])

    client = AsyncTavilyClient(api_key=key)

    async def one(q: str) -> dict[str, Any]:
        try:
            resp = await client.search(q, max_results=max_results)
            results = resp.get("results", []) if isinstance(resp, dict) else resp
            return {"query": q, "results": results}
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return {"query": q, "error": str(exc), "results": []}

    return await asyncio.gather(*[one(q) for q in queries])


def build_investment_research_tools(max_results: int = 5) -> list[Any]:
    """Expose TavilySearchResults for LangChain tool binding (optional)."""
    tool = build_tavily_search_tool(max_results=max_results)
    return [tool] if tool is not None else []


def build_investment_tavily_queries(location: str, country: str, raw_query: str = "") -> list[str]:
    loc = location.strip() or "the region"
    ctry = country.strip() or "the country"
    lower_q = raw_query.lower()

    queries = [
        f"property tax stamp duty home buyer regulations {loc} {ctry} 2025 2026",
        f"infrastructure development commercial projects real estate impact {loc} {ctry} 2025 2026",
        f"average property price trends residential listings {loc} {ctry} 2025 2026",
    ]

    # Context-specific queries extracted from what the user actually asked about
    if any(kw in lower_q for kw in ["flood", "ravi", "river", "water", "rain", "inundation", "drainage"]):
        queries.append(f"flood risk Ravi river property value impact {loc} {ctry} 2024 2025")

    if any(kw in lower_q for kw in ["crime", "security", "safe", "unsafe", "theft", "dangerous"]):
        queries.append(f"crime rate safety neighborhood {loc} {ctry} 2025")

    if any(kw in lower_q for kw in ["school", "education", "university", "college"]):
        queries.append(f"schools universities education facilities near {loc} {ctry}")

    if any(kw in lower_q for kw in ["hospital", "health", "medical", "clinic"]):
        queries.append(f"hospitals medical facilities near {loc} {ctry}")

    if any(kw in lower_q for kw in ["road", "transport", "metro", "commute", "traffic", "highway"]):
        queries.append(f"transport connectivity roads metro infrastructure {loc} {ctry} 2025")

    return queries
