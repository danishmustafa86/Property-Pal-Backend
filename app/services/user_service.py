from fastapi import HTTPException, status

from app.repositories.users import UserRepository
from app.schemas.common import serialize_mongo_id
from app.schemas.user import UserProfileUpdate


class UserService:
    def __init__(self) -> None:
        self.repo = UserRepository()

    async def get_me(self, user: dict) -> dict:
        doc = await self.repo.get_by_id(user["id"])
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return serialize_mongo_id(doc)

    async def update_me(self, user: dict, payload: UserProfileUpdate) -> dict:
        update_payload = payload.model_dump(exclude_none=True)
        requested_role = update_payload.get("role")
        if requested_role == "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot self-assign admin role.")

        doc = await self.repo.update_profile(user["id"], update_payload)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return serialize_mongo_id(doc)
