from app.agents.parser import QueryParser


def test_parser_lahore_crore():
    data = QueryParser().parse("Find me 5 marla house in Lahore under 1 crore").model_dump(exclude_none=True)
    assert data["city"] == "Lahore"
    assert data["property_type"] == "house"
    assert data["max_price"] == 10_000_000
    assert data["min_marlas"] == 5


def test_parser_canal_road_rent():
    q = (
        "show me houses for family in canal road with nearby mosques, schools, "
        "restaurants under 3 lacs rent, with 5 beds"
    )
    data = QueryParser().parse(q).model_dump(exclude_none=True)
    assert data["purpose"] == "rent"
    assert data["max_price"] == 300_000
    assert data["keyword"] == "Canal Road"
    assert data["rooms"] == 5
    assert set(data["near_place_types"]) == {"mosque", "school", "restaurant"}
