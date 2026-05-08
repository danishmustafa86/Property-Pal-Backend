from bson import ObjectId
from pymongo import DESCENDING

from app.models.collections import PROPERTIES_COLLECTION
from app.repositories.base import BaseRepository


class PropertyRepository(BaseRepository):
    collection_name = PROPERTIES_COLLECTION

    async def create(self, owner_user_id: str, payload: dict):
        now = self.now()
        payload.update(
            {
                "owner_user_id": owner_user_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        result = await self.collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    async def get_by_id(self, property_id: str):
        return await self.collection.find_one({"_id": ObjectId(property_id)})

    async def list_for_owner(self, owner_user_id: str):
        return await self.collection.find({"owner_user_id": owner_user_id}).sort("updated_at", DESCENDING).to_list(length=200)

    async def update_property(self, property_id: str, payload: dict):
        return await self.update_one_return_doc(ObjectId(property_id), payload)

    async def delete_property(self, property_id: str, owner_user_id: str):
        result = await self.collection.delete_one({"_id": ObjectId(property_id), "owner_user_id": owner_user_id})
        return result.deleted_count > 0
