from fastapi import HTTPException, status

from app.repositories.agents import AgentRepository
from app.repositories.users import UserRepository
from app.schemas.agent import AgentProfileCreate, AgentProfileUpdate
from app.schemas.common import serialize_mongo_id


class AgentService:
    def __init__(self) -> None:
        self.repo = AgentRepository()
        self.users = UserRepository()

    async def create(self, user: dict, payload: AgentProfileCreate) -> dict:
        existing = await self.repo.get_by_user_id(user["id"])
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent profile already exists.")

        data = payload.model_dump()
        data["name"] = user.get("full_name") or "Agent"
        data["email"] = user.get("email") or ""
        doc = await self.repo.create(user_id=user["id"], payload=data)
        serialized = serialize_mongo_id(doc)
        await self.users.update_profile(
            user["id"],
            {
                "role": "agent",
                "agent_profile_id": serialized["id"],
            },
        )
        return serialized

    async def get_my_profile(self, user: dict) -> dict:
        doc = await self.repo.get_by_user_id(user["id"])
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent profile not found.")
        return serialize_mongo_id(doc)

    async def update_my_profile(self, user: dict, payload: AgentProfileUpdate) -> dict:
        doc = await self.repo.get_by_user_id(user["id"])
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent profile not found.")
        update_data = payload.model_dump(exclude_none=True)
        if not update_data:
            return serialize_mongo_id(doc)
        updated = await self.repo.update_agent(str(doc["_id"]), update_data)
        return serialize_mongo_id(updated)

    async def list_agents(self) -> list[dict]:
        return [serialize_mongo_id(x) for x in await self.repo.list_agents()]

    async def get_agent(self, agent_id: str) -> dict:
        doc = await self.repo.get_by_id(agent_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
        return serialize_mongo_id(doc)
