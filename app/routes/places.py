"""Google Places API routes — nearby places lookup, property enrichment, area summaries."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import current_user
from app.services.places_service import PLACE_TYPE_LABELS, PLACE_TYPE_MAP, PlacesService

router = APIRouter()
_places = PlacesService()


@router.get("/types")
async def get_supported_place_types():
    """List all supported place type categories with display labels."""
    return {
        "place_types": [
            {"key": k, "label": PLACE_TYPE_LABELS.get(k, k.title())}
            for k in PLACE_TYPE_MAP
        ]
    }


@router.get("/nearby")
async def get_nearby_places(
    lat: float = Query(..., ge=-90, le=90, description="Property latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Property longitude"),
    place_type: str = Query(..., description="hospital | mosque | school | restaurant | market | pharmacy | park | bank | gym"),
    radius_km: float = Query(default=2.0, gt=0, le=10, description="Search radius in kilometres"),
    max_results: int = Query(default=10, ge=1, le=20),
):
    """
    Get nearby places of a specific type around a coordinate pair.
    Used by the frontend property detail page to show real nearby amenities.
    """
    if place_type not in PLACE_TYPE_MAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported place_type '{place_type}'. Valid: {list(PLACE_TYPE_MAP.keys())}",
        )
    if not _places.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API is not configured on this server.",
        )
    results = await _places.nearby_search(
        lat, lng, place_type, radius_m=radius_km * 1000, max_results=max_results
    )
    return {
        "place_type": place_type,
        "label": PLACE_TYPE_LABELS.get(place_type, place_type.title()),
        "latitude": lat,
        "longitude": lng,
        "radius_km": radius_km,
        "count": len(results),
        "places": results,
    }


@router.get("/property/{property_id}")
async def get_all_nearby_for_property(
    property_id: str,
    radius_km: float = Query(default=2.0, gt=0, le=10),
):
    """
    Return all amenity categories near a property (by its ID).
    Reads from the pre-enriched `nearby_places` field in MongoDB — no live API call.
    Falls back to a live fetch if the property hasn't been enriched yet.
    """
    from app.db.mongodb import get_database
    from bson import ObjectId
    from app.schemas.common import serialize_mongo_id

    try:
        oid = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid property_id.")

    prop = await get_database()["properties"].find_one({"_id": oid})
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found.")

    stored = prop.get("nearby_places") or []
    if stored:
        # Group stored data by category for the frontend
        by_cat: dict[str, list] = {}
        for p in stored:
            cat = p.get("place_type", "other")
            by_cat.setdefault(cat, []).append(p)
        return {
            "property_id": property_id,
            "source": "cached",
            "categories": [
                {
                    "place_type": cat,
                    "label": PLACE_TYPE_LABELS.get(cat, cat.title()),
                    "count": len(places),
                    "places": places,
                }
                for cat, places in by_cat.items()
            ],
        }

    # Property not yet enriched — live fetch
    lat, lng = prop.get("latitude"), prop.get("longitude")
    if not lat or not lng:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Property has no coordinates; cannot fetch nearby places.",
        )
    if not _places.is_configured():
        return {"property_id": property_id, "source": "unavailable", "categories": []}

    enriched = await _places.enrich_property_places(lat, lng, radius_m=radius_km * 1000)
    all_places = enriched.get("nearby_places", [])

    by_cat = {}
    for p in all_places:
        cat = p.get("place_type", "other")
        by_cat.setdefault(cat, []).append(p)

    return {
        "property_id": property_id,
        "source": "live",
        "categories": [
            {
                "place_type": cat,
                "label": PLACE_TYPE_LABELS.get(cat, cat.title()),
                "count": len(places),
                "places": places,
            }
            for cat, places in by_cat.items()
        ],
    }


@router.get("/area-summary")
async def get_area_amenity_summary(
    city: str = Query(..., min_length=2, description="City name e.g. Lahore, Karachi"),
    sub_location: str = Query(default="", description="Sub-area e.g. DHA, Bahria Town"),
    radius_km: float = Query(default=3.0, gt=0, le=10),
):
    """
    Get a structured amenity summary for a city/area.
    Used by the frontend map overview.
    """
    if not _places.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API is not configured on this server.",
        )
    summary = await _places.get_area_amenity_summary(city, sub_location, radius_m=radius_km * 1000)
    if "error" in summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=summary["error"])
    return summary


@router.post("/enrich/{property_id}")
async def enrich_property_with_places(
    property_id: str,
    radius_km: float = Query(default=2.0, gt=0, le=10),
    user: dict = Depends(current_user),
):
    """
    Manually trigger Google Places enrichment for an existing property.
    Fetches real nearby hospitals, mosques, schools, etc. and persists them to MongoDB.
    Requires authentication (owner, agent, or admin).
    """
    if not _places.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API is not configured on this server.",
        )

    from app.db.mongodb import get_database
    from bson import ObjectId

    try:
        oid = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid property_id.")

    prop = await get_database()["properties"].find_one({"_id": oid})
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found.")

    lat, lng = prop.get("latitude"), prop.get("longitude")
    if not lat or not lng:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Property has no coordinates.",
        )

    enriched = await _places.enrich_property_places(lat, lng, radius_m=radius_km * 1000)
    await get_database()["properties"].update_one({"_id": oid}, {"$set": enriched})

    return {
        "message": "Property enriched successfully with Google Places data.",
        "property_id": property_id,
        "places_found": len(enriched.get("nearby_places", [])),
        "categories_populated": {
            "nearby_schools": len(enriched.get("nearby_schools", [])),
            "nearby_mosques": len(enriched.get("nearby_mosques", [])),
            "nearby_markets": len(enriched.get("nearby_markets", [])),
            "nearby_restaurants": len(enriched.get("nearby_restaurants", [])),
        },
    }
