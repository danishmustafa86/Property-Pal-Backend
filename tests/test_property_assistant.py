from app.agents.parser import QueryParser
from app.agents.property_assistant import _is_help_query, _is_out_of_scope


def test_help_query():
    assert _is_help_query("how can you help me") is True
    assert _is_help_query("what can you do") is True


def test_parser_ignores_help_phrase_keyword():
    data = QueryParser().parse("how can you help me").model_dump(exclude_none=True)
    assert "keyword" not in data


def test_parser_defaults_to_house():
    data = QueryParser().parse("5 bed for rent in Lahore under 50 lac").model_dump(exclude_none=True)
    assert data["property_type"] == "house"
    assert data["city"] == "Lahore"


def test_out_of_scope_investment_advice():
    assert _is_out_of_scope("Best investment areas in Lahore") is True


def test_out_of_scope_should_i_buy():
    assert _is_out_of_scope("should I buy in Bahria Town Rawalpindi right now?") is True


def test_in_scope_listing_search_with_investment_word():
    assert _is_out_of_scope("5 bed house for rent in Lahore under 50 lac") is False
