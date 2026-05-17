from app.utils.search_match import filter_listings, listing_matches_filters


def test_matches_canal_road_rent():
    listing = {
        "title": "Canal Road House",
        "location": "Canal Road",
        "city": "Faisalabad",
        "price": 250_000,
        "number_of_bedrooms": 5,
        "nearby_places": [
            {"place_type": "mosque"},
            {"place_type": "school"},
            {"place_type": "restaurant"},
        ],
    }
    filters = {
        "max_price": 300_000,
        "keyword": "canal road",
        "rooms": 5,
        "max_rooms": 5,
        "near_place_types": ["mosque", "school", "restaurant"],
    }
    assert listing_matches_filters(listing, filters)


def test_rejects_over_budget():
    listing = {"location": "Canal Road", "price": 500_000, "number_of_bedrooms": 5}
    assert not listing_matches_filters(listing, {"max_price": 300_000})


def test_filter_listings():
    items = [
        {"location": "Canal Road", "price": 200_000, "number_of_bedrooms": 5},
        {"location": "Jaranwala Road", "price": 500_000, "number_of_bedrooms": 8},
    ]
    out = filter_listings(items, {"max_price": 300_000, "keyword": "canal road", "rooms": 5, "max_rooms": 5})
    assert len(out) == 1
