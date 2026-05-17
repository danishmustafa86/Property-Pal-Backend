"""Google Places API (New) integration for nearby amenity lookups and property enrichment."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
_FIELD_MASK = (
    "places.id,places.displayName,places.types,"
    "places.formattedAddress,places.rating,places.location,"
    "places.regularOpeningHours.openNow"
)

# Our category → Google place types (New API type names)
PLACE_TYPE_MAP: dict[str, list[str]] = {
    "hospital":   ["hospital"],
    "mosque":     ["mosque"],
    "school":     ["school", "primary_school", "secondary_school"],
    "university": ["university"],
    "restaurant": ["restaurant"],
    "market":     ["grocery_store", "supermarket", "shopping_mall"],
    "pharmacy":   ["pharmacy"],
    "park":       ["park"],
    "bank":       ["bank", "atm"],
    "gym":        ["gym"],
    "gas_station":["gas_station"],
}

# Display labels for the frontend
PLACE_TYPE_LABELS: dict[str, str] = {
    "hospital":   "Hospitals & Clinics",
    "mosque":     "Mosques",
    "school":     "Schools",
    "university": "Universities",
    "restaurant": "Restaurants",
    "market":     "Markets & Supermarkets",
    "pharmacy":   "Pharmacies",
    "park":       "Parks",
    "bank":       "Banks & ATMs",
    "gym":        "Gyms",
    "gas_station":"Petrol Stations",
}

# Pakistani city centre coordinates (lat, lng)
CITY_COORDS: dict[str, tuple[float, float]] = {
    "lahore":        (31.5204, 74.3587),
    "karachi":       (24.8607, 67.0011),
    "islamabad":     (33.6844, 73.0479),
    "rawalpindi":    (33.5651, 73.0169),
    "faisalabad":    (31.4504, 73.1350),
    "multan":        (30.1575, 71.5249),
    "peshawar":      (34.0150, 71.5249),
    "gujranwala":    (32.1877, 74.1945),
    "sialkot":       (32.4945, 74.5229),
    "quetta":        (30.1798, 66.9750),
    "hyderabad":     (25.3960, 68.3578),
    "abbottabad":    (34.1463, 73.2117),
    "bahawalpur":    (29.3956, 71.6836),
    "sargodha":      (32.0836, 72.6711),
    "sukkur":        (27.7052, 68.8574),
    "larkana":       (27.5570, 68.2120),
    "rahim yar khan":(28.4212, 70.2957),
    "sheikhupura":   (31.7167, 73.9850),
}


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two WGS-84 coordinate pairs."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return round(R * 2 * math.asin(math.sqrt(max(0.0, a))), 1)


def _city_coords(city: str) -> tuple[float, float] | None:
    key = city.lower().strip()
    if key in CITY_COORDS:
        return CITY_COORDS[key]
    # Partial match (e.g. "Lahore DHA" → "lahore")
    for k, v in CITY_COORDS.items():
        if k in key or key in k:
            return v
    return None


class PlacesService:
    """Async Google Places API (New) client."""

    def __init__(self) -> None:
        self._api_key = (settings.google_maps_api_key or "").strip()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    # ── Core API call ──────────────────────────────────────────────────────────

    async def nearby_search(
        self,
        lat: float,
        lng: float,
        place_category: str,
        radius_m: float = 2000,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Return nearby places of `place_category` sorted by distance from (lat, lng)."""
        if not self.is_configured():
            logger.warning("GOOGLE_MAPS_API_KEY not configured — skipping Places lookup.")
            return []

        google_types = PLACE_TYPE_MAP.get(place_category.lower(), [place_category])
        body = {
            "includedTypes": google_types,
            "maxResultCount": min(max_results, 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_m),
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(_PLACES_NEARBY_URL, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Places API HTTP %s for category=%s: %s",
                exc.response.status_code, place_category, exc.response.text[:400],
            )
            return []
        except Exception as exc:
            logger.error("Places API request failed for category=%s: %s", place_category, exc)
            return []

        places: list[dict[str, Any]] = []
        for p in data.get("places", []):
            loc = p.get("location") or {}
            p_lat = loc.get("latitude")
            p_lng = loc.get("longitude")
            dist = _haversine_meters(lat, lng, p_lat, p_lng) if p_lat is not None and p_lng is not None else None
            places.append({
                "place_id":        p.get("id", ""),
                "name":            (p.get("displayName") or {}).get("text", "Unknown"),
                "place_type":      place_category,
                "distance_meters": dist,
                "rating":          p.get("rating"),
                "address":         p.get("formattedAddress"),
                "open_now":        (p.get("regularOpeningHours") or {}).get("openNow"),
                "latitude":        p_lat,
                "longitude":       p_lng,
            })

        places.sort(key=lambda x: x.get("distance_meters") or 99_999)
        return places

    # ── Property enrichment ────────────────────────────────────────────────────

    async def enrich_property_places(
        self, lat: float, lng: float, radius_m: float = 2000
    ) -> dict[str, Any]:
        """
        Fetch all amenity categories near a property coordinate.
        Returns both structured `nearby_places` and legacy string-list fields.
        """
        if not self.is_configured():
            return {"nearby_places": []}

        categories = ["hospital", "mosque", "school", "restaurant", "market", "pharmacy", "park"]
        tasks = [
            self.nearby_search(lat, lng, cat, radius_m=radius_m, max_results=4)
            for cat in categories
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_places: list[dict[str, Any]] = []
        legacy: dict[str, list[str]] = {cat: [] for cat in categories}

        for cat, res in zip(categories, results):
            if isinstance(res, Exception):
                logger.warning("Places lookup error for %s: %s", cat, res)
                continue
            for place in res:
                all_places.append(place)
                legacy[cat].append(place["name"])

        return {
            "nearby_places":      all_places,
            # Legacy string fields — now backed by real Google data
            "nearby_schools":     legacy["school"][:4],
            "nearby_mosques":     legacy["mosque"][:4],
            "nearby_markets":     legacy["market"][:4],
            "nearby_restaurants": legacy["restaurant"][:4],
        }

    # ── Area summary (for agent) ───────────────────────────────────────────────

    async def get_area_amenity_summary(
        self, city: str, sub_location: str = "", radius_m: float = 3000
    ) -> dict[str, Any]:
        """
        Amenity summary for an area.
        Resolves city to lat/lng using a built-in coordinate table.
        """
        if not self.is_configured():
            return {"error": "Google Maps API key not configured.", "amenities": {}}

        coords = _city_coords(city)
        if coords is None:
            return {"error": f"No coordinates found for city: {city!r}", "amenities": {}}

        lat, lng = coords
        enriched = await self.enrich_property_places(lat, lng, radius_m=radius_m)
        all_places = enriched.get("nearby_places", [])

        by_cat: dict[str, list[dict]] = {}
        for p in all_places:
            by_cat.setdefault(p["place_type"], []).append(p)

        amenities: dict[str, Any] = {}
        for cat, places in by_cat.items():
            closest = places[0]
            amenities[cat] = {
                "label":              PLACE_TYPE_LABELS.get(cat, cat.title()),
                "count":              len(places),
                "nearest_name":       closest["name"],
                "nearest_distance_m": closest.get("distance_meters"),
                "nearest_rating":     closest.get("rating"),
                "top_3":              [p["name"] for p in places[:3]],
            }

        return {
            "city":               city,
            "sub_location":       sub_location,
            "search_radius_m":    radius_m,
            "total_found":        len(all_places),
            "amenities":          amenities,
        }

    # ── Proximity scoring helper ───────────────────────────────────────────────

    def places_proximity_score(
        self, nearby_places: list[dict], place_type: str, max_distance_m: float = 2000
    ) -> float:
        """
        Score 0.0-1.0 based on distance to the nearest place of the requested type.
        1.0 = right next door, 0.0 = not found or beyond max_distance.
        """
        matching = [p for p in nearby_places if p.get("place_type") == place_type]
        if not matching:
            return 0.0
        closest = min(p.get("distance_meters") or max_distance_m for p in matching)
        return max(0.0, 1.0 - closest / max_distance_m)
