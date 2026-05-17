"""
LangChain tools for the location-aware property assistant.

Each tool is an async function decorated with @tool.  The LLM calls these
based on user intent — no regex or hard-wired flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

import certifi
import httpx
from langchain_core.tools import tool
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.schemas.common import serialize_mongo_id
from app.services.places_service import PlacesService, PLACE_TYPE_LABELS

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# ── Price normaliser ──────────────────────────────────────────────────────────
# The LLM sometimes passes the raw number from the user's query (e.g. 1 for
# "1 lac") instead of the PKR value (100 000).  We detect suspiciously small
# values and convert them automatically.

def _to_pkr(price: int | float | None) -> int | None:
    """Normalise a price that might be in lacs/crores to PKR."""
    if price is None:
        return None
    price = float(price)
    if price <= 0:
        return None
    # Values < 1 000 are almost certainly in lac (minimum real rent ≥ 10 000 PKR)
    if price < 1_000:
        return int(price * 100_000)   # e.g. 1 → 100 000,  1.5 → 150 000
    # Values between 1 000 and 9 999 could be "10 lac" range — leave as-is
    # (a legit 5 000 PKR rent makes no sense in Pakistan)
    return int(price)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_collection():
    uri = settings.mongodb_uri
    kwargs: dict = {}
    if "mongodb+srv://" in uri.lower() or "tls=true" in uri.lower():
        kwargs["tlsCAFile"] = certifi.where()
    client = AsyncIOMotorClient(uri, **kwargs)
    return client[settings.mongodb_db_name]["properties"]


def _fmt_price(price: int) -> str:
    if price >= 10_000_000:
        return f"{price / 10_000_000:.1f} Crore"
    if price >= 100_000:
        return f"{price / 100_000:.1f} Lac"
    return f"{price / 1_000:.0f}K"


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(R * 2 * math.asin(math.sqrt(max(0.0, a))), 0)


def _slim(doc: dict, search_lat: float | None = None, search_lng: float | None = None) -> dict:
    """Return a compact property dict safe to include in tool output."""
    area = doc.get("area") or {}
    out: dict[str, Any] = {
        "id":          doc.get("id") or str(doc.get("_id", "")),
        "title":       doc.get("title", ""),
        "city":        doc.get("city", ""),
        "location":    doc.get("location", ""),
        "price":       doc.get("price", 0),
        "price_fmt":   _fmt_price(doc.get("price", 0)),
        "purpose":     doc.get("purpose", ""),
        "property_type": doc.get("property_type", ""),
        "bedrooms":    doc.get("number_of_bedrooms", 0),
        "bathrooms":   doc.get("number_of_bathrooms", 0),
        "area":        area,
        "latitude":    doc.get("latitude"),
        "longitude":   doc.get("longitude"),
        "images":      (doc.get("images") or [])[:1],
        "nearby_places": doc.get("nearby_places") or [],
    }
    if search_lat is not None and search_lng is not None:
        lat = doc.get("latitude")
        lng = doc.get("longitude")
        if lat and lng:
            out["distance_from_search_m"] = _haversine_m(search_lat, search_lng, lat, lng)
    return out


# ── Tool 1: geocode_location ──────────────────────────────────────────────────

@tool
async def geocode_location(query: str) -> str:
    """
    Convert a place name or address into GPS coordinates (latitude, longitude).

    Use this tool whenever the user mentions a specific area, neighbourhood,
    landmark, or city in Pakistan — e.g. "DHA Phase 5 Lahore", "Johar Town",
    "Samundri Road Faisalabad", "near Jinnah Hospital".

    Returns JSON: {"lat": float, "lng": float, "formatted_address": str}
    or {"error": "..."} on failure.
    """
    api_key = settings.google_maps_api_key
    if not api_key:
        return json.dumps({"error": "Google Maps API key not configured"})

    params = {
        "address":    f"{query}, Pakistan",
        "key":        api_key,
        "region":     "pk",
        "components": "country:PK",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(_GEOCODE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("geocode_location failed for %r: %s", query, exc)
        return json.dumps({"error": str(exc)})

    if data.get("status") != "OK" or not data.get("results"):
        return json.dumps({"error": f"No results for {query!r}"})

    r = data["results"][0]
    loc = r["geometry"]["location"]
    return json.dumps({
        "lat": round(loc["lat"], 6),
        "lng": round(loc["lng"], 6),
        "formatted_address": r.get("formatted_address", query),
    })


# ── Tool 2: find_properties_near_location ─────────────────────────────────────

@tool
async def find_properties_near_location(
    lat: float,
    lng: float,
    radius_km: float = 15.0,
    purpose: str | None = None,
    property_type: str | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    max_results: int = 10,
) -> str:
    """
    Find active property listings closest to the given GPS coordinates.

    Use this AFTER geocode_location to find houses near a specific place.
    Results are sorted nearest-first and include distance_from_search_m.

    Args:
        lat: latitude from geocode_location
        lng: longitude from geocode_location
        radius_km: search radius in kilometres (default 15 — use 15-20 for Pakistani cities)
        purpose: "rent" or "buy" (optional)
        property_type: "house", "apartment", "plot" etc. (optional)
        max_price: budget ceiling in PKR — ALWAYS convert first: 1 lac=100000, 1 crore=10000000
        min_bedrooms: minimum number of bedrooms (optional)
        max_results: max properties to return (default 10)

    Returns JSON list of matching properties sorted by distance.
    """
    col = _get_collection()
    max_price = _to_pkr(max_price)

    base_filter: dict[str, Any] = {"listing_status": "active"}
    if purpose:
        base_filter["purpose"] = purpose
    if property_type:
        base_filter["property_type"] = property_type
    if max_price:
        base_filter["price"] = {"$lte": max_price}
    if min_bedrooms:
        base_filter["number_of_bedrooms"] = {"$gte": min_bedrooms}

    # Auto-expand: try radius_km, then double up to 30km if too few results
    docs: list = []
    used_radius = radius_km
    for attempt_radius in [radius_km, min(radius_km * 2, 30.0), 30.0]:
        mongo_filter = {
            **base_filter,
            "geo_point": {
                "$nearSphere": {
                    "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "$maxDistance": int(attempt_radius * 1000),
                }
            },
        }
        try:
            docs = await col.find(mongo_filter).limit(max_results).to_list(length=max_results)
        except Exception as exc:
            logger.error("find_properties_near_location failed: %s", exc)
            return json.dumps({"error": str(exc), "results": []})
        used_radius = attempt_radius
        if len(docs) >= 3:
            break  # enough results — no need to expand further

    results = [_slim(serialize_mongo_id(d), search_lat=lat, search_lng=lng) for d in docs]
    return json.dumps({
        "count": len(results),
        "search_lat": lat,
        "search_lng": lng,
        "radius_km_used": used_radius,
        "results": results,
    })


# ── Tool 3: search_properties ─────────────────────────────────────────────────

@tool
async def search_properties(
    city: str | None = None,
    purpose: str | None = None,
    property_type: str | None = None,
    max_price: int | None = None,
    min_price: int | None = None,
    min_bedrooms: int | None = None,
    max_bedrooms: int | None = None,
    keyword: str | None = None,
    furnished: bool | None = None,
    garage: bool | None = None,
    max_results: int = 10,
) -> str:
    """
    Search active property listings by filters (no location proximity needed).

    Use this for general searches like "3 bed house for rent in Lahore under 50k"
    or "furnished apartment in Islamabad".

    Args:
        city: city name e.g. "Lahore", "Faisalabad", "Karachi"
        purpose: "rent" or "buy"
        property_type: "house", "apartment", "plot", "shop", "office"
        max_price: budget ceiling in PKR — ALWAYS convert: 1 lac=100000, 1 crore=10000000, 80k=80000
        min_price: budget floor in PKR — same conversion rules
        min_bedrooms: minimum bedrooms
        max_bedrooms: exact/maximum bedrooms
        keyword: free-text area name e.g. "DHA Phase 6", "Canal Road"
        furnished: True for furnished only
        garage: True for garage/parking required
        max_results: max to return (default 10)

    Returns JSON list of matching properties.
    """
    col = _get_collection()
    mongo_filter: dict[str, Any] = {"listing_status": "active"}
    max_price = _to_pkr(max_price)
    min_price = _to_pkr(min_price)

    if city:
        mongo_filter["city"] = {"$regex": city, "$options": "i"}
    if purpose:
        mongo_filter["purpose"] = purpose
    if property_type:
        mongo_filter["property_type"] = {"$regex": property_type, "$options": "i"}

    price_q: dict = {}
    if min_price:
        price_q["$gte"] = min_price
    if max_price:
        price_q["$lte"] = max_price
    if price_q:
        mongo_filter["price"] = price_q

    beds_q: dict = {}
    if min_bedrooms:
        beds_q["$gte"] = min_bedrooms
    if max_bedrooms:
        beds_q["$lte"] = max_bedrooms
    if beds_q:
        mongo_filter["number_of_bedrooms"] = beds_q

    if furnished is True:
        mongo_filter["$or"] = [
            {"title": {"$regex": "furnished", "$options": "i"}},
            {"description": {"$regex": "furnished", "$options": "i"}},
        ]
    if garage is True:
        mongo_filter["garage"] = True

    if keyword:
        kw_re = {"$regex": keyword, "$options": "i"}
        kw_cond = [
            {"location": kw_re}, {"society": kw_re},
            {"title": kw_re}, {"description": kw_re},
        ]
        if "$or" in mongo_filter:
            mongo_filter["$and"] = [{"$or": mongo_filter.pop("$or")}, {"$or": kw_cond}]
        else:
            mongo_filter["$or"] = kw_cond

    try:
        docs = (
            await col.find(mongo_filter)
            .sort("quality_score", -1)
            .limit(max_results)
            .to_list(length=max_results)
        )
    except Exception as exc:
        logger.error("search_properties failed: %s", exc)
        return json.dumps({"error": str(exc), "results": []})

    results = [_slim(serialize_mongo_id(d)) for d in docs]
    return json.dumps({"count": len(results), "results": results})


# ── Tool 4: get_amenities_near_location ───────────────────────────────────────

@tool
async def get_amenities_near_location(
    lat: float,
    lng: float,
    amenity_types: list[str],
    radius_m: int = 2000,
) -> str:
    """
    Find hospitals, mosques, schools, restaurants, markets, parks, pharmacies,
    or gyms near a specific GPS coordinate using Google Maps Places API.

    Use this when the user asks "what's near X?" or wants to know about
    facilities around a particular place or address.

    amenity_types: list of any of: hospital, mosque, school, university,
                   restaurant, market, pharmacy, park, gym, bank

    Returns JSON dict: { "hospital": [{name, distance_meters, rating, address}] }
    """
    svc = PlacesService()
    if not svc.is_configured():
        return json.dumps({"error": "Google Maps API key not configured"})

    valid_types = [t for t in amenity_types if t in PLACE_TYPE_LABELS]
    if not valid_types:
        return json.dumps({"error": f"Unknown amenity types. Valid: {list(PLACE_TYPE_LABELS)}"})

    tasks = [svc.nearby_search(lat, lng, t, radius_m=radius_m, max_results=5) for t in valid_types]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    output: dict[str, Any] = {}
    for t, res in zip(valid_types, raw_results):
        if isinstance(res, Exception):
            output[t] = {"error": str(res)}
        else:
            output[t] = {
                "label": PLACE_TYPE_LABELS.get(t, t),
                "count": len(res),
                "places": [
                    {
                        "name": p["name"],
                        "distance_m": p.get("distance_meters"),
                        "rating": p.get("rating"),
                        "address": p.get("address"),
                    }
                    for p in res
                ],
            }
    return json.dumps(output)


# ── Tool 5: find_properties_ranked_by_amenities ───────────────────────────────

@tool
async def find_properties_ranked_by_amenities(
    amenity_types: list[str],
    lat: float | None = None,
    lng: float | None = None,
    search_radius_km: float = 15.0,
    city: str | None = None,
    purpose: str | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    keyword: str | None = None,
    amenity_radius_m: int = 2000,
    max_results: int = 10,
) -> str:
    """
    Find properties near a location and rank them by how many of the requested
    amenities (hospitals, mosques, schools, restaurants, etc.) are nearby.

    This is the BEST tool when the user says things like:
    - "houses near City Housing Faisalabad with hospitals and schools"
    - "apartment with schools and markets nearby in Lahore"
    - "which houses have most amenities near Johar Town"

    ALWAYS pass lat/lng from geocode_location when the user mentions a specific
    place — this uses proximity search, not just city filter.

    Args:
        amenity_types: list from: hospital, mosque, school, restaurant, market,
                       pharmacy, park, gym, university, bank
        lat: latitude from geocode_location (pass this for proximity search)
        lng: longitude from geocode_location
        search_radius_km: km radius to find candidate properties (default 15)
        city: fallback city filter if no lat/lng
        purpose: "rent" or "buy"
        max_price: in PKR — convert: 1 lac=100000, 1 crore=10000000
        min_bedrooms: minimum bedrooms
        keyword: area/society name for text filter
        amenity_radius_m: metres to search for each amenity type around a property
        max_results: max to return (default 10)

    Returns JSON list sorted by amenity_score (most amenities first).
    """
    col = _get_collection()
    max_price = _to_pkr(max_price)

    base_filter: dict[str, Any] = {"listing_status": "active"}
    if purpose:
        base_filter["purpose"] = purpose
    if max_price:
        base_filter["price"] = {"$lte": max_price}
    if min_bedrooms:
        base_filter["number_of_bedrooms"] = {"$gte": min_bedrooms}
    if keyword:
        kw_re = {"$regex": keyword, "$options": "i"}
        base_filter["$or"] = [{"location": kw_re}, {"society": kw_re}, {"title": kw_re}]

    # Prefer proximity search when coordinates are available
    if lat is not None and lng is not None:
        # Auto-expand radius if needed (same pattern as find_properties_near_location)
        docs: list = []
        used_radius = search_radius_km
        for attempt_radius in [search_radius_km, min(search_radius_km * 2, 30.0), 30.0]:
            mongo_filter = {
                **base_filter,
                "geo_point": {
                    "$nearSphere": {
                        "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                        "$maxDistance": int(attempt_radius * 1000),
                    }
                },
            }
            try:
                docs = await col.find(mongo_filter).limit(25).to_list(length=25)
            except Exception as exc:
                return json.dumps({"error": str(exc), "results": []})
            used_radius = attempt_radius
            if len(docs) >= 5:
                break
    else:
        # Fall back to city/keyword filter
        if city:
            base_filter["city"] = {"$regex": city, "$options": "i"}
        used_radius = None
        try:
            docs = (
                await col.find(base_filter)
                .sort("quality_score", -1)
                .limit(25)
                .to_list(length=25)
            )
        except Exception as exc:
            return json.dumps({"error": str(exc), "results": []})

    if not docs:
        return json.dumps({"count": 0, "results": []})

    svc = PlacesService()
    valid_types = [t for t in amenity_types if t in PLACE_TYPE_LABELS]

    async def _score_property(doc: dict) -> dict:
        p_lat = doc.get("latitude")
        p_lng = doc.get("longitude")
        slim = _slim(serialize_mongo_id(doc))

        if not p_lat or not p_lng or not svc.is_configured() or not valid_types:
            slim["amenity_score"] = 0
            slim["amenity_summary"] = {}
            return slim

        # Check if property already has cached nearby_places for these types
        cached = {p["place_type"]: p for p in (doc.get("nearby_places") or [])}
        needed = [t for t in valid_types if t not in cached]

        if needed:
            tasks = [svc.nearby_search(p_lat, p_lng, t, radius_m=amenity_radius_m, max_results=3) for t in needed]
            fetched = await asyncio.gather(*tasks, return_exceptions=True)
            new_places: list[dict] = []
            for t, res in zip(needed, fetched):
                if not isinstance(res, Exception):
                    new_places.extend(res)
            slim["nearby_places"] = list(
                {p["place_type"]: p for p in [*slim.get("nearby_places", []), *new_places]}.values()
            )

        # Score: +1 per amenity type found, +0.5 bonus if within half the search radius
        score = 0
        summary: dict[str, dict] = {}
        for t in valid_types:
            matching = [p for p in slim["nearby_places"] if p.get("place_type") == t]
            if matching:
                closest_m = min(p.get("distance_meters") or amenity_radius_m for p in matching)
                score += 1 + (0.5 if closest_m < amenity_radius_m / 2 else 0)
                summary[t] = {
                    "count": len(matching),
                    "nearest_name": matching[0]["name"],
                    "nearest_distance_m": int(closest_m),
                }

        slim["amenity_score"] = round(score, 2)
        slim["amenity_summary"] = summary
        # Attach distance from the user's searched location
        if lat is not None and lng is not None:
            slim["distance_from_search_m"] = _haversine_m(lat, lng, p_lat, p_lng)
        return slim

    # Score all candidates concurrently (semaphore to limit parallel API calls)
    sem = asyncio.Semaphore(5)

    async def _scored(doc: dict) -> dict:
        async with sem:
            return await _score_property(doc)

    scored_docs = await asyncio.gather(*[_scored(d) for d in docs])
    scored_docs.sort(key=lambda x: x.get("amenity_score", 0), reverse=True)
    top = scored_docs[:max_results]

    return json.dumps({
        "count": len(top),
        "search_lat": lat,
        "search_lng": lng,
        "search_radius_km_used": used_radius,
        "amenity_types_searched": valid_types,
        "results": top,
    })


# ── Tool 6: find_houses_near_place (combined — preferred for place searches) ──

@tool
async def find_houses_near_place(
    location_query: str,
    amenity_types: list[str] | None = None,
    purpose: str | None = None,
    max_price: int | None = None,
    min_bedrooms: int | None = None,
    radius_km: float = 15.0,
    max_results: int = 10,
) -> str:
    """
    ONE-STEP tool: finds properties near any Pakistani place name.

    Internally geocodes the location then searches for the nearest properties,
    optionally ranking them by nearby amenities.

    USE THIS as the primary tool whenever the user mentions any specific:
    - neighbourhood / housing society (e.g. "City Housing Samundari Road", "DHA Phase 5")
    - landmark / hospital / road / area
    - any place in Pakistan

    You do NOT need to call geocode_location separately — this tool does it all.

    Args:
        location_query: the place the user mentioned, e.g.
                        "City Housing Samundari Road Faisalabad"
                        "DHA Phase 6 Lahore"
                        "near Jinnah Hospital Karachi"
        amenity_types: optional list of amenities to rank by —
                       hospital, mosque, school, restaurant, market, park, pharmacy, gym
        purpose: "rent" or "buy"
        max_price: in PKR — convert: 1 lac=100000, 1 crore=10000000
        min_bedrooms: minimum bedrooms
        radius_km: search radius (default 15 km — good for Pakistani cities)
        max_results: max properties to return (default 10)

    Returns JSON with geocoded address, property list, distances, and amenity scores.
    """
    # Step 1: geocode the location string
    geo_raw = await geocode_location.ainvoke({"query": location_query})
    try:
        geo = json.loads(geo_raw)
    except Exception:
        return json.dumps({"error": f"Geocoding failed for {location_query!r}", "results": []})

    if "error" in geo:
        return json.dumps({
            "error": f"Could not find coordinates for {location_query!r}: {geo['error']}",
            "results": [],
        })

    s_lat: float = geo["lat"]
    s_lng: float = geo["lng"]
    address: str = geo.get("formatted_address", location_query)

    max_price_pkr = _to_pkr(max_price)

    # Step 2a: if amenity ranking requested → find_properties_ranked_by_amenities
    if amenity_types:
        amenity_raw = await find_properties_ranked_by_amenities.ainvoke({
            "amenity_types": amenity_types,
            "lat": s_lat,
            "lng": s_lng,
            "search_radius_km": radius_km,
            "purpose": purpose,
            "max_price": max_price_pkr,
            "min_bedrooms": min_bedrooms,
            "max_results": max_results,
        })
        try:
            data = json.loads(amenity_raw)
        except Exception:
            data = {"results": []}
        data["geocoded_address"] = address
        return json.dumps(data)

    # Step 2b: plain proximity search
    near_raw = await find_properties_near_location.ainvoke({
        "lat": s_lat,
        "lng": s_lng,
        "radius_km": radius_km,
        "purpose": purpose,
        "max_price": max_price_pkr,
        "min_bedrooms": min_bedrooms,
        "max_results": max_results,
    })
    try:
        data = json.loads(near_raw)
    except Exception:
        data = {"results": []}
    data["geocoded_address"] = address
    return json.dumps(data)
