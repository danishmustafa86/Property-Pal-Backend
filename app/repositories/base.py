from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from app.db.mongodb import get_database


class BaseRepository:
    collection_name: str

    @property
    def collection(self):
        return get_database()[self.collection_name]

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def to_object_id(value: str) -> ObjectId:
        return ObjectId(value)

    async def update_one_return_doc(self, object_id: ObjectId, payload: dict):
        payload["updated_at"] = self.now()
        return await self.collection.find_one_and_update(
            {"_id": object_id},
            {"$set": payload},
            return_document=ReturnDocument.AFTER,
        )
