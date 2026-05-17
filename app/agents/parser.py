import re

from app.schemas.search import SearchFilters


class QueryParser:
    """Deterministic parser: natural language → MongoDB search filters."""

    _LAC = r"(?:lakh|lacs?)\b"
    _NEARBY_WORDS: dict[str, tuple[str, ...]] = {
        "hospital": ("hospital", "hospitals", "clinic", "clinics"),
        "mosque": ("mosque", "mosques", "masjid", "masjids"),
        "school": ("school", "schools", "academy", "academies"),
        "university": ("university", "universities", "college", "colleges"),
        "restaurant": ("restaurant", "restaurants", "cafe", "cafes", "food street"),
        "market": ("market", "markets", "bazaar", "mall", "supermarket"),
        "pharmacy": ("pharmacy", "pharmacies", "chemist"),
        "park": ("park", "parks", "garden", "gardens"),
        "gym": ("gym", "gyms", "fitness"),
    }

    CITY_KEYWORDS = [
        "rahim yar khan", "lahore", "karachi", "islamabad", "rawalpindi",
        "faisalabad", "gujranwala", "sheikhupura", "bahawalpur", "hyderabad",
        "multan", "peshawar", "sargodha", "abbottabad", "sialkot", "quetta",
        "larkana", "sukkur",
    ]
    PROPERTY_TYPES = [
        "penthouse", "farmhouse", "warehouse", "apartment", "villa",
        "office", "house", "shop", "flat", "plot",
    ]

    def parse(self, query: str) -> SearchFilters:
        lower = query.lower()
        payload: dict = {}

        for city in self.CITY_KEYWORDS:
            if city in lower:
                payload["city"] = city.title()
                break

        if re.search(r"\b(?:rent|rental|renting|for\s+rent)\b", lower):
            payload["purpose"] = "rent"
        if re.search(r"\b(?:buy|buying|purchase|for\s+sale|to\s+buy)\b", lower):
            payload["purpose"] = "buy"

        for ptype in self.PROPERTY_TYPES:
            if re.search(rf"\b{re.escape(ptype)}s?\b", lower):
                payload["property_type"] = "apartment" if ptype == "flat" else ptype
                break

        kanal_m = re.search(r"(\d+(?:\.\d+)?)\s*kanal", lower)
        if kanal_m:
            marlas = float(kanal_m.group(1)) * 20
            payload["min_marlas"] = marlas
            payload["max_marlas"] = marlas

        marla_m = re.search(r"(\d+(?:\.\d+)?)\s*marla", lower)
        if marla_m:
            marla = float(marla_m.group(1))
            payload["min_marlas"] = marla
            payload["max_marlas"] = marla

        crore_m = re.search(
            r"(?:under|below|max|less\s+than|upto|up\s+to|within)?\s*"
            r"(\d+(?:\.\d+)?)\s*crore",
            lower,
        )
        if crore_m:
            payload["max_price"] = int(float(crore_m.group(1)) * 10_000_000)

        if "max_price" not in payload:
            lakh_m = re.search(
                rf"(?:under|below|max|less\s+than|upto|up\s+to|within)?\s*"
                rf"(\d+(?:\.\d+)?)\s*{self._LAC}",
                lower,
            )
            if lakh_m:
                payload["max_price"] = int(float(lakh_m.group(1)) * 100_000)

        if "max_price" not in payload:
            monthly_m = re.search(r"(\d[\d,]+)\s*(?:monthly|per\s+month|/\s*month)\b", lower)
            if monthly_m:
                val = int(monthly_m.group(1).replace(",", ""))
                if val >= 1000:
                    payload["max_price"] = val

        if "max_price" not in payload:
            plain = re.search(
                r"(?:under|below|less\s+than|max|upto)\s+(?:rs\.?\s*|pkr\.?\s*)?(\d[\d,]+)",
                lower,
            )
            if plain:
                val = int(plain.group(1).replace(",", ""))
                if val >= 5000:
                    payload["max_price"] = val

        min_crore = re.search(r"(?:above|over|from|min)\s+(\d+(?:\.\d+)?)\s*crore", lower)
        if min_crore:
            payload["min_price"] = int(float(min_crore.group(1)) * 10_000_000)

        if re.search(r"\b(?:fully\s+)?furnished\b", lower):
            payload["furnished"] = True
        elif re.search(r"\bunfurnished\b", lower):
            payload["furnished"] = False

        if re.search(r"\b(?:with\s+)?garage\b|\bparking\b", lower):
            payload["garage"] = True
        if re.search(r"\bnew\s+construction\b|\bbrand\s+new\b|\bnewly\s+built\b", lower):
            payload["new_construction"] = True

        near_types: list[str] = []
        _near_prefix = (
            r"(?:near|nearby|close\s+to|next\s+to)\s+(?:a\s+|an\s+|the\s+)?"
        )
        for place_type, words in self._NEARBY_WORDS.items():
            for w in words:
                if re.search(_near_prefix + re.escape(w), lower) or (
                    re.search(r"\b(?:near|nearby)\b", lower)
                    and re.search(rf"\b{re.escape(w)}\b", lower)
                ):
                    if place_type not in near_types:
                        near_types.append(place_type)
                    break
        if near_types:
            payload["near_place_types"] = near_types
            payload["near_place_type"] = near_types[0]

        loc_m = re.search(
            r"\bin\s+([a-z0-9][a-z0-9\s\-]{2,48}?)"
            r"(?=\s+(?:with|near|under|for|,)|$)",
            lower,
        )
        if loc_m:
            loc = re.sub(r"\s+", " ", loc_m.group(1).strip())
            if len(loc) >= 3 and loc not in {c.lower() for c in self.CITY_KEYWORDS}:
                payload["keyword"] = loc.title()

        bed_m = re.search(r"(\d+)\s*(?:bed(?:room)?s?|bhk)\b", lower)
        if bed_m:
            n = int(bed_m.group(1))
            payload["rooms"] = n
            if not re.search(r"\b(?:at\s+least|minimum|min|\+)\b", lower):
                payload["max_rooms"] = n

        bath_m = re.search(r"(\d+)\s*bath(?:room)?s?\b", lower)
        if bath_m:
            payload["bathrooms"] = int(bath_m.group(1))

        total_m = re.search(r"(\d+)\s+(?:total\s+)?rooms?\b", lower)
        if total_m and "bed" not in lower[max(0, total_m.start() - 12) : total_m.end() + 12]:
            payload["total_rooms"] = int(total_m.group(1))

        quoted = re.search(r"['\"]([^'\"]{4,120})['\"]", query)
        if quoted:
            payload["keyword"] = quoted.group(1).strip()
        elif "keyword" not in payload:
            city_pat = "|".join(re.escape(c) for c in self.CITY_KEYWORDS)
            type_pat = "|".join(self.PROPERTY_TYPES)
            noise = (
                rf"\b({city_pat}|{type_pat}|"
                r"rent|buy|sale|bed|beds|bath|baths|marla|kanal|crore|lakh|lac|lacs|pkr|"
                r"show|find|near|nearby|family|furnished|unfurnished|garage|parking|monthly|to|"
                r"mosque|mosques|school|schools|hospital|hospitals|restaurant|restaurants|"
                r"market|markets|park|parks|gym|gyms|fully|with|and|the|in|for|under|"
                r"houses|apartments|flats|plots|villas|shops|offices|"
                r"how|what|can|you|help|me|do|who|hello|hi|hey|this|work)\b"
            )
            cleaned = re.sub(noise, " ", lower)
            cleaned = re.sub(r"\b\d+(?:\.\d+)?(?:k|cr|lac|lakh|lacs?|crore)?\b", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if len(cleaned) >= 4:
                payload["keyword"] = cleaned[:120].title()

        if "property_type" not in payload:
            payload["property_type"] = "house"

        return SearchFilters(**payload)
