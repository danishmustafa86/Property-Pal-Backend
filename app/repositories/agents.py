from bson import ObjectId
from pymongo import ReturnDocument

from app.models.collections import AGENTS_COLLECTION
from app.repositories.base import BaseRepository


class AgentRepository(BaseRepository):
    collection_name = AGENTS_COLLECTION

    async def create(self, user_id: str, payload: dict):
        now = self.now()
        payload.update({"user_id": user_id, "created_at": now, "updated_at": now})
        result = await self.collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    async def list_agents(self):
        return await self.collection.find({}).to_list(length=100)

    async def get_by_id(self, agent_id: str):
        return await self.collection.find_one({"_id": ObjectId(agent_id)})

    async def get_by_user_id(self, user_id: str):
        return await self.collection.find_one({"user_id": user_id})

    async def update_agent(self, agent_id: str, payload: dict):
        payload["updated_at"] = self.now()
        return await self.collection.find_one_and_update(
            {"_id": ObjectId(agent_id)},
            {"$set": payload},
            return_document=ReturnDocument.AFTER,
        )
