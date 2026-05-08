from datetime import datetime, timezone

from app.services.ranking_service import RankingService


def test_ranking_returns_numeric_score():
    service = RankingService()
    listing = {
        "title": "5 Marla House DHA",
        "description": "Beautiful house",
        "city": "Lahore",
        "price": 25_000_000,
        "updated_at": datetime.now(timezone.utc),
        "quality_score": 90,
        "views_count": 100,
        "saves_count": 10,
        "inquiry_count": 3,
    }
    query = {"city": "Lahore", "keyword": "house", "min_price": 20_000_000, "max_price": 30_000_000}
    score = service.score(listing, query)
    assert isinstance(score, float)
    assert 0 <= score <= 100
