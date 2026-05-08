from bson import ObjectId

from app.db.mongodb import get_database
from app.schemas.common import serialize_mongo_id
from app.schemas.search import SearchRequest
from app.services.ranking_service import RankingService
from app.utils.area import to_sqft
from app.utils.pagination import decode_cursor, encode_cursor


class SearchService:
    def __init__(self) -> None:
        self.ranking = RankingService()

    @property
    def collection(self):
        return get_database()["properties"]

    @staticmethod
    def _build_filter(search: SearchRequest) -> dict:
        query: dict = {"listing_status": "active"}
        if search.city:
            query["city"] = search.city
        if search.purpose:
            query["purpose"] = search.purpose
        if search.property_type:
            query["property_type"] = search.property_type
        if search.min_price is not None or search.max_price is not None:
            price_q = {}
            if search.min_price is not None:
                price_q["$gte"] = search.min_price
            if search.max_price is not None:
                price_q["$lte"] = search.max_price
            query["price"] = price_q
        if search.min_marlas is not None or search.max_marlas is not None:
            area_q = {}
            if search.min_marlas is not None:
                area_q["$gte"] = to_sqft(search.min_marlas, "marla")
            if search.max_marlas is not None:
                area_q["$lte"] = to_sqft(search.max_marlas, "marla")
            query["area.value_sqft_normalized"] = area_q
        if search.rooms is not None:
            query["number_of_bedrooms"] = {"$gte": search.rooms}
        if search.bathrooms is not None:
            query["number_of_bathrooms"] = {"$gte": search.bathrooms}
        if search.new_construction is not None:
            query["new_construction"] = search.new_construction
        if search.garage is not None:
            query["garage"] = search.garage
        if search.min_construction_year is not None or search.max_construction_year is not None:
            year_q = {}
            if search.min_construction_year is not None:
                year_q["$gte"] = search.min_construction_year
            if search.max_construction_year is not None:
                year_q["$lte"] = search.max_construction_year
            query["construction_year"] = year_q
        if search.latitude and search.longitude and search.radius_km:
            query["geo_point"] = {
                "$near": {
                    "$geometry": {"type": "Point", "coordinates": [search.longitude, search.latitude]},
                    "$maxDistance": int(search.radius_km * 1000),
                }
            }
        if search.keyword:
            query["$text"] = {"$search": search.keyword}
        return query

    async def search(self, search: SearchRequest) -> dict:
        mongo_filter = self._build_filter(search)
        if search.cursor:
            cursor_data = decode_cursor(search.cursor)
            mongo_filter["_id"] = {"$lt": ObjectId(cursor_data["id"])}

        cursor = (
            self.collection.find(mongo_filter)
            .sort([("updated_at", -1), ("_id", -1)])
            .limit(search.page_size + 1)
        )
        rows = await cursor.to_list(length=search.page_size + 1)
        has_next = len(rows) > search.page_size
        rows = rows[: search.page_size]

        next_cursor = None
        if has_next and rows:
            last = rows[-1]
            next_cursor = encode_cursor(last["updated_at"], str(last["_id"]))

        scored = []
        query_dict = search.model_dump(exclude_none=True)
        for row in rows:
            row["score"] = self.ranking.score(row, query_dict)
            scored.append(serialize_mongo_id(row))
        scored.sort(key=lambda x: x["score"], reverse=True)

        return {"items": scored, "next_cursor": next_cursor}
