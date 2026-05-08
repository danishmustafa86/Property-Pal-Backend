from fastapi import APIRouter, Depends

from app.auth.dependencies import current_user
from app.schemas.user import UserProfileUpdate
from app.services.user_service import UserService

router = APIRouter()
service = UserService()


@router.get("/")
async def get_me(user: dict = Depends(current_user)):
    return await service.get_me(user)


@router.patch("/")
async def update_me(payload: UserProfileUpdate, user: dict = Depends(current_user)):
    return await service.update_me(user, payload)
