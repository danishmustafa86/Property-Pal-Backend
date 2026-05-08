from app.db.mongodb import get_database
from app.schemas.common import serialize_mongo_id
from app.schemas.search import MapViewportQuery
from app.services.ranking_service import RankingService


class MapService:
    def __init__(self) -> None:
        self.ranking = RankingService()

    @property
    def collection(self):
        return get_database()["properties"]

    async def search_in_viewport(self, query: MapViewportQuery) -> list[dict]:
        mongo_filter: dict = {
            "listing_status": "active",
            "geo_point": {
                "$geoWithin": {
                    "$box": [
                        [query.min_lng, query.min_lat],
                        [query.max_lng, query.max_lat],
                    ]
                }
            },
        }
        if query.purpose:
            mongo_filter["purpose"] = query.purpose
        if query.property_type:
            mongo_filter["property_type"] = query.property_type

        docs = await self.collection.find(mongo_filter).limit(1000).to_list(length=1000)
        markers = []
        for doc in docs:
            serialized = serialize_mongo_id(doc)
            coords = serialized.get("geo_point", {}).get("coordinates", [0, 0])
            markers.append(
                {
                    "id": serialized["id"],
                    "lat": coords[1],
                    "lng": coords[0],
                    "price": serialized["price"],
                    "purpose": serialized["purpose"],
                    "property_type": serialized["property_type"],
                    "thumbnail": (serialized.get("images") or [None])[0],
                    "score": self.ranking.score(serialized, query.model_dump(exclude_none=True)),
                }
            )
        return sorted(markers, key=lambda m: m["score"], reverse=True)
