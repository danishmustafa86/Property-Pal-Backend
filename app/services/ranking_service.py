from datetime import datetime, timezone


class RankingService:
    """Simple configurable ranking score for listings."""

    def score(self, listing: dict, query: dict) -> float:
        freshness = self._freshness_score(listing)
        quality = min(float(listing.get("quality_score", 0)) / 100.0, 1.0)
        engagement = self._engagement_score(listing)
        price_fit = self._price_fit_score(listing, query)
        geo_fit = self._geo_fit_score(listing, query)
        text_match = self._text_match_score(listing, query)

        total = (
            (0.20 * freshness)
            + (0.20 * quality)
            + (0.15 * engagement)
            + (0.20 * price_fit)
            + (0.15 * geo_fit)
            + (0.10 * text_match)
        )
        return round(total * 100, 2)

    def _freshness_score(self, listing: dict) -> float:
        updated_at = listing.get("updated_at")
        if not updated_at:
            return 0.3
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - updated_at).days, 0)
        return max(0.0, 1 - (age_days / 120))

    def _engagement_score(self, listing: dict) -> float:
        views = listing.get("views_count", 0)
        saves = listing.get("saves_count", 0)
        inquiries = listing.get("inquiry_count", 0)
        score = (views * 0.02) + (saves * 0.15) + (inquiries * 0.25)
        return min(score / 10, 1.0)

    def _price_fit_score(self, listing: dict, query: dict) -> float:
        min_price = query.get("min_price")
        max_price = query.get("max_price")
        price = listing.get("price", 0)
        if not min_price and not max_price:
            return 0.5
        if min_price and price < min_price:
            return 0
        if max_price and price > max_price:
            return 0
        return 1.0

    def _geo_fit_score(self, listing: dict, query: dict) -> float:
        if not query.get("city"):
            return 0.5
        return 1.0 if listing.get("city", "").lower() == query["city"].lower() else 0.2

    def _text_match_score(self, listing: dict, query: dict) -> float:
        keyword = (query.get("keyword") or "").strip().lower()
        if not keyword:
            return 0.5
        text = f"{listing.get('title', '')} {listing.get('description', '')}".lower()
        return 1.0 if keyword in text else 0.1
