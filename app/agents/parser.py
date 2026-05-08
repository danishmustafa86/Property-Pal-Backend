import re

from app.schemas.search import SearchFilters


class QueryParser:
    """Deterministic fallback parser for common Pakistani real-estate phrasing."""

    CITY_KEYWORDS = ["lahore", "karachi", "islamabad", "rawalpindi", "faisalabad", "multan", "peshawar"]
    PROPERTY_TYPES = ["house", "plot", "shop", "apartment", "office", "warehouse", "farmhouse"]

    def parse(self, query: str) -> SearchFilters:
        lower = query.lower()
        payload: dict = {}

        for city in self.CITY_KEYWORDS:
            if city in lower:
                payload["city"] = city.title()
                break

        if "rent" in lower:
            payload["purpose"] = "rent"
        if "buy" in lower or "sale" in lower:
            payload["purpose"] = "buy"

        for ptype in self.PROPERTY_TYPES:
            if ptype in lower:
                payload["property_type"] = ptype
                break

        marla_match = re.search(r"(\d+(\.\d+)?)\s*marla", lower)
        if marla_match:
            marla = float(marla_match.group(1))
            payload["min_marlas"] = marla
            payload["max_marlas"] = marla

        under_match = re.search(r"under\s+(\d+)\s*crore", lower)
        if under_match:
            payload["max_price"] = int(under_match.group(1)) * 10_000_000

        budget_match = re.search(r"(\d+)\s*lakh", lower)
        if budget_match and "max_price" not in payload:
            payload["max_price"] = int(budget_match.group(1)) * 100_000

        # "100000 monthly" / "100000 per month" / "100000/month" — rent context
        if "max_price" not in payload:
            monthly_m = re.search(r"(\d[\d,]+)\s*(?:monthly|per\s+month|/\s*month|a\s+month)\b", lower)
            if monthly_m:
                val = int(monthly_m.group(1).replace(",", ""))
                if val >= 1000:
                    payload["max_price"] = val

        # "under/below/less than N" with a plain number (not crore/lakh)
        if "max_price" not in payload:
            plain_cap = re.search(
                r"(?:under|below|less than|max(?:imum)?|upto|up to)\s+(?:rs\.?\s*|pkr\.?\s*)?(\d[\d,]+)",
                lower,
            )
            if plain_cap:
                val = int(plain_cap.group(1).replace(",", ""))
                if val >= 5000:
                    payload["max_price"] = val

        # "under/below Nk" — thousands shorthand (e.g. "under 80k")
        if "max_price" not in payload:
            k_m = re.search(r"(?:under|below|less than|max(?:imum)?|within|budget)\s+(\d+)\s*k\b", lower)
            if k_m:
                val = int(k_m.group(1)) * 1000
                if val >= 5000:
                    payload["max_price"] = val

        room_match = re.search(r"(\d+)\s*(bed|bedroom|rooms?)", lower)
        if room_match:
            payload["rooms"] = int(room_match.group(1))

        bath_match = re.search(r"(\d+)\s*(bath|bathroom)", lower)
        if bath_match:
            payload["bathrooms"] = int(bath_match.group(1))

        # Try to capture quoted listing titles or specific keyword phrases.
        quoted = re.search(r"['\"]([^'\"]{4,120})['\"]", query)
        if quoted:
            payload["keyword"] = quoted.group(1).strip()
        elif "keyword" not in payload:
            # Keep meaningful text as a fallback keyword if request is mostly unstructured.
            city_pattern = "|".join(self.CITY_KEYWORDS)
            ptype_pattern = "|".join(self.PROPERTY_TYPES) + "|" + "|".join(
                p + "s" for p in self.PROPERTY_TYPES
            )
            cleaned = re.sub(
                rf"\b({city_pattern}|{ptype_pattern}|in|for|under|over|above|below|less|than|more|buy|sale|sell|rent|"
                r"flat|flats|bed|bedroom|bedrooms|bath|bathroom|bathrooms|marla|crore|lakh|"
                r"pkr|rs|monthly|per|month|week|year|daily|show|find|me|get|available|want|looking|need|with|"
                r"and|a|an|the|around|within|budget|max|minimum|maximum|upto|up|to|property|properties)\b",
                " ",
                lower,
            )
            cleaned = re.sub(r"\b\d+\b", " ", cleaned)  # strip numbers captured as price/rooms
            cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if len(cleaned) >= 4:
                payload["keyword"] = cleaned[:120]

        return SearchFilters(**payload)
