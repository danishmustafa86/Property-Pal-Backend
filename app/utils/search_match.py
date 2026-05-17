"""Validate listing rows against parsed assistant filters."""

from __future__ import annotations


def listing_matches_filters(listing: dict, filters: dict) -> bool:
    if not filters:
        return True

    price = listing.get("price") or 0
    if filters.get("min_price") is not None and price < filters["min_price"]:
        return False
    if filters.get("max_price") is not None and price > filters["max_price"]:
        return False

    keyword = (filters.get("keyword") or "").strip().lower()
    if keyword:
        hay = " ".join(
            str(listing.get(k) or "") for k in ("title", "location", "city", "description")
        ).lower()
        if keyword not in hay:
            return False

    beds = listing.get("number_of_bedrooms")
    rooms = filters.get("rooms")
    max_rooms = filters.get("max_rooms")
    if rooms is not None and beds is not None:
        if max_rooms is not None:
            if not (rooms <= beds <= max_rooms):
                return False
        elif beds < rooms:
            return False

    total_rooms = filters.get("total_rooms")
    if total_rooms is not None:
        n = listing.get("number_of_rooms")
        if n is None or n < total_rooms:
            return False

    baths = filters.get("bathrooms")
    if baths is not None:
        b = listing.get("number_of_bathrooms")
        if b is None or b < baths:
            return False

    ptype = filters.get("property_type")
    if ptype and (listing.get("property_type") or "").lower() != str(ptype).lower():
        return False

    if filters.get("garage") is True and not listing.get("garage"):
        return False
    if filters.get("new_construction") is True and not listing.get("new_construction"):
        return False

    furnished = filters.get("furnished")
    if furnished is not None:
        text = f"{listing.get('title', '')} {listing.get('description', '')}".lower()
        has_furnished = "furnished" in text
        if furnished and not has_furnished:
            return False
        if furnished is False and has_furnished:
            return False

    place_types = filters.get("near_place_types") or []
    if not place_types and filters.get("near_place_type"):
        place_types = [filters["near_place_type"]]
    if place_types:
        nearby = listing.get("nearby_places") or []
        for pt in place_types:
            if not any(p.get("place_type") == pt for p in nearby):
                return False

    return True


def filter_listings(items: list[dict], filters: dict) -> list[dict]:
    if not filters:
        return items
    return [item for item in items if listing_matches_filters(item, filters)]
