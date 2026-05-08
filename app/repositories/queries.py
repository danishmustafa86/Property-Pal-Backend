from bson import ObjectId

from app.models.collections import QUERY_HISTORY_COLLECTION, SAVED_SEARCHES_COLLECTION
from app.repositories.base import BaseRepository


class QueryRepository(BaseRepository):
    collection_name = QUERY_HISTORY_COLLECTION

    async def create_query_record(self, user_id: str, query: str, interpreted_filters: dict):
        payload = {
            "user_id": user_id,
            "query": query,
            "interpreted_filters": interpreted_filters,
            "created_at": self.now(),
            "updated_at": self.now(),
        }
        result = await self.collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    async def get_history(self, user_id: str, limit: int = 20):
        return await self.collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit).to_list(length=limit)


class SavedSearchRepository(BaseRepository):
    collection_name = SAVED_SEARCHES_COLLECTION

    async def save(self, user_id: str, filters: dict, name: str | None = None):
        payload = {
            "user_id": user_id,
            "filters": filters,
            "name": name or "Saved Search",
            "created_at": self.now(),
            "updated_at": self.now(),
        }
        result = await self.collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    async def list_saved(self, user_id: str):
        return await self.collection.find({"user_id": user_id}).sort("updated_at", -1).to_list(length=200)

    async def delete_saved(self, user_id: str, saved_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(saved_id), "user_id": user_id})
        return result.deleted_count > 0
