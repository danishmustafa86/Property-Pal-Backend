"""Google Geocoding API — convert place names / addresses to lat/lng coordinates."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Accurate coordinates for Pakistani neighbourhoods.
# Keys are lowercase; values are (latitude, longitude).
# Lookup order: exact → partial-match → Google Geocoding API.
_LOCAL_COORDS: dict[str, tuple[float, float]] = {
    # ── Faisalabad ────────────────────────────────────────────────────────────
    "canal road":               (31.4268, 73.0882),
    "madina town":              (31.4387, 73.1039),
    "peoples colony":           (31.4451, 73.1011),
    "satiana road":             (31.4634, 73.1723),
    "eden valley":              (31.4623, 73.0970),
    "wapda city":               (31.4297, 73.1278),
    "susan road":               (31.4544, 73.1103),
    "d ground":                 (31.4148, 73.0902),
    "jinnah colony":            (31.4046, 73.0967),
    "ghulam muhammad abad":     (31.4202, 73.1298),
    "samanabad":                (31.4574, 73.0750),
    "millat town":              (31.4774, 73.0901),
    "jaranwala road":           (31.4819, 73.2121),
    "chenab gardens":           (31.4005, 73.1002),
    "abdullah pur":             (31.4110, 73.0998),
    "kotwali road":             (31.4189, 73.0950),
    "sargodha road":            (31.4680, 73.0818),
    "nishatabad":               (31.4305, 73.1506),
    "kohinoor city":            (31.4423, 73.1623),
    "civil lines faisalabad":   (31.4273, 73.1253),
    "jhang road":               (31.4158, 73.0702),
    "samundri road":            (31.4140, 73.0720),
    "samundari road":           (31.4140, 73.0720),
    "city housing":             (31.4050, 73.0810),
    "city housing faisalabad":  (31.4050, 73.0810),
    "lyallpur town":            (31.4598, 73.1022),
    "gulberg faisalabad":       (31.4338, 73.1060),

    # ── Lahore ────────────────────────────────────────────────────────────────
    "dha lahore":               (31.4697, 74.3814),
    "dha phase 6":              (31.4622, 74.3740),
    "dha phase 8":              (31.4370, 74.3620),
    "bahria town lahore":       (31.3626, 74.1748),
    "johar town":               (31.4696, 74.2728),
    "wapda town":               (31.4444, 74.2651),
    "model town":               (31.5031, 74.3323),
    "gulberg":                  (31.5100, 74.3477),
    "gulberg lahore":           (31.5100, 74.3477),
    "garden town":              (31.4993, 74.3108),
    "iqbal town":               (31.4761, 74.3032),
    "township":                 (31.4610, 74.2510),
    "faisal town":              (31.4814, 74.2847),
    "valencia":                 (31.5303, 74.3917),
    "lahore cantt":             (31.5497, 74.3879),
    "cavalry ground":           (31.5306, 74.3815),
    "thokar niaz baig":         (31.3917, 74.2008),
    "lake city":                (31.5651, 74.4752),
    "paragon city":             (31.3793, 74.2183),

    # ── Islamabad ─────────────────────────────────────────────────────────────
    "f-7":                      (33.7215, 73.0618),
    "f-8":                      (33.7142, 73.0463),
    "f-10":                     (33.7050, 73.0289),
    "f-11":                     (33.7195, 73.0150),
    "g-10":                     (33.6796, 73.0447),
    "g-11":                     (33.6705, 73.0311),
    "g-13":                     (33.6596, 73.0175),
    "g-15":                     (33.6410, 72.9963),
    "b-17":                     (33.6408, 72.9120),
    "dha islamabad":            (33.5400, 73.1100),
    "bahria town islamabad":    (33.4836, 73.0479),
    "blue area":                (33.7276, 73.0954),
    "i-8":                      (33.6776, 73.0686),
    "i-10":                     (33.6617, 73.0782),
    "e-11":                     (33.7261, 72.9963),

    # ── Rawalpindi ────────────────────────────────────────────────────────────
    "bahria town rwp":          (33.4836, 73.0479),
    "bahria town rawalpindi":   (33.4836, 73.0479),
    "pwd":                      (33.6480, 73.1027),
    "adyala road":              (33.5416, 73.0073),
    "saddar rawalpindi":        (33.6007, 73.0679),
    "chaklala scheme":          (33.6137, 73.1037),
    "dha phase 2 rawalpindi":   (33.5300, 73.1250),
    "satellite town rawalpindi":(33.5882, 73.0726),

    # ── Karachi ───────────────────────────────────────────────────────────────
    "clifton":                  (24.8098, 67.0366),
    "dha karachi":              (24.7978, 67.0534),
    "gulshan-e-iqbal":          (24.9268, 67.0942),
    "gulshan e iqbal":          (24.9268, 67.0942),
    "scheme 33":                (24.9543, 67.1285),
    "north nazimabad":          (24.9400, 67.0454),
    "pechs":                    (24.8603, 67.0619),
    "defence karachi":          (24.7978, 67.0534),
    "bahria town karachi":      (24.8623, 67.1697),
    "malir":                    (24.8893, 67.1982),

    # ── Peshawar ──────────────────────────────────────────────────────────────
    "hayatabad":                (33.9970, 71.4531),
    "university town":          (34.0064, 71.4791),
    "saddar peshawar":          (34.0102, 71.5785),

    # ── Other Punjab ──────────────────────────────────────────────────────────
    "dha multan":               (30.1218, 71.5004),
    "gulgasht colony":          (30.1960, 71.4780),
}


class GeocodingService:
    """Async Google Geocoding API wrapper."""

    def __init__(self) -> None:
        self._api_key = (settings.google_maps_api_key or "").strip()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def geocode(self, query: str, country_code: str = "pk") -> tuple[float, float] | None:
        """
        Convert a place name / address to (lat, lng).
        Returns None if geocoding fails or the address is ambiguous.
        """
        # Fast path: exact match in local table (no API call needed)
        local = _LOCAL_COORDS.get(query.lower().strip())
        if local:
            logger.debug("Geocode fast-path hit for %r: %s", query, local)
            return local

        # Partial match: "Canal Road Faisalabad" → matches "canal road"
        lower = query.lower().strip()
        for key, coords in _LOCAL_COORDS.items():
            if key in lower:
                logger.debug("Geocode partial-match for %r → %r: %s", query, key, coords)
                return coords

        if not self.is_configured():
            logger.warning("GOOGLE_MAPS_API_KEY not set — geocoding unavailable for %r", query)
            return None

        params: dict[str, str] = {
            "address": query,
            "key": self._api_key,
            "region": country_code,
            "components": f"country:{country_code.upper()}",
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(_GEOCODE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Geocoding request failed for %r: %s", query, exc)
            return None

        if data.get("status") != "OK" or not data.get("results"):
            logger.debug("Geocoding returned status=%s for %r", data.get("status"), query)
            return None

        loc = data["results"][0]["geometry"]["location"]
        result = (float(loc["lat"]), float(loc["lng"]))
        logger.info("Geocoded %r → %s", query, result)
        return result

    async def reverse_geocode(self, lat: float, lng: float) -> dict[str, Any]:
        """Convert lat/lng to a structured address (city, area, etc.)."""
        if not self.is_configured():
            return {}
        params = {"latlng": f"{lat},{lng}", "key": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json", params=params
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Reverse geocoding failed: %s", exc)
            return {}

        if data.get("status") != "OK" or not data.get("results"):
            return {}

        components: dict[str, str] = {}
        for comp in data["results"][0].get("address_components", []):
            for t in comp.get("types", []):
                components[t] = comp.get("long_name", "")

        return {
            "formatted_address": data["results"][0].get("formatted_address"),
            "city": components.get("locality") or components.get("administrative_area_level_2"),
            "province": components.get("administrative_area_level_1"),
            "country": components.get("country"),
            "postal_code": components.get("postal_code"),
        }
