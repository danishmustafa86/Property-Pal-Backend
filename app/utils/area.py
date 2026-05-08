MARLA_TO_SQFT = 272.25
KANAL_TO_SQFT = 20 * MARLA_TO_SQFT
SQYD_TO_SQFT = 9.0


def to_sqft(value: float, unit: str) -> float:
    normalized = unit.lower()
    if normalized == "marla":
        return value * MARLA_TO_SQFT
    if normalized == "kanal":
        return value * KANAL_TO_SQFT
    if normalized == "sqyd":
        return value * SQYD_TO_SQFT
    return value


def sqft_to_marla(value_sqft: float) -> float:
    return value_sqft / MARLA_TO_SQFT
