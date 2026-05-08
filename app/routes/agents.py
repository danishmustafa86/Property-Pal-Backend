from fastapi import APIRouter, Depends

from app.auth.dependencies import current_user, current_user_optional
from app.schemas.agent import AgentProfileCreate, AgentProfileUpdate
from app.services.agent_service import AgentService

router = APIRouter()
service = AgentService()


@router.post("/")
async def create_agent_profile(payload: AgentProfileCreate, user: dict = Depends(current_user)):
    return await service.create(user, payload)


@router.get("/me")
async def get_my_agent_profile(user: dict = Depends(current_user)):
    return await service.get_my_profile(user)


@router.put("/me")
async def update_my_agent_profile(payload: AgentProfileUpdate, user: dict = Depends(current_user)):
    return await service.update_my_profile(user, payload)


@router.get("/")
async def list_agents(_: dict | None = Depends(current_user_optional)):
    return await service.list_agents()


@router.get("/{agent_id}")
async def get_agent(agent_id: str, _: dict | None = Depends(current_user_optional)):
    return await service.get_agent(agent_id)
