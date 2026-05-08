from app.agents.parser import QueryParser


def test_parser_extracts_common_fields():
    parser = QueryParser()
    filters = parser.parse("Find me 5 marla house in Lahore under 1 crore")
    data = filters.model_dump(exclude_none=True)
    assert data["city"] == "Lahore"
    assert data["property_type"] == "house"
    assert data["max_price"] == 10_000_000
    assert data["min_marlas"] == 5
