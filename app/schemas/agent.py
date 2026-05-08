from datetime import datetime

from app.schemas.common import MongoModel


class AgentProfileBase(MongoModel):
    name: str
    company: str | None = None
    phone: str
    email: str
    city: str
    years_experience: int = 0
    bio: str | None = None


class AgentProfileCreate(MongoModel):
    company: str | None = None
    phone: str
    city: str
    years_experience: int = 0
    bio: str | None = None


class AgentProfileUpdate(MongoModel):
    company: str | None = None
    phone: str | None = None
    city: str | None = None
    years_experience: int | None = None
    bio: str | None = None


class AgentProfileOut(AgentProfileBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
