from datetime import datetime
from typing import Literal

from app.schemas.common import MongoModel


UserRole = Literal["user", "agent", "admin"]


class UserProfile(MongoModel):
    id: str
    clerk_user_id: str
    email: str
    full_name: str
    role: UserRole = "user"
    phone: str | None = None
    phone_verified: bool = False
    agent_profile_id: str | None = None
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(MongoModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    role: Literal["user", "agent"] | None = None
