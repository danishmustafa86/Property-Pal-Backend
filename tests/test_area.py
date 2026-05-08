from app.utils.area import sqft_to_marla, to_sqft


def test_marla_conversion_roundtrip():
    sqft = to_sqft(5, "marla")
    marlas = sqft_to_marla(sqft)
    assert round(marlas, 2) == 5.00
