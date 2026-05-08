from datetime import datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class MongoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class TimestampMixin(MongoModel):
    created_at: datetime
    updated_at: datetime


class PaginatedResponse(MongoModel):
    items: list[Any]
    next_cursor: str | None = None
    total: int | None = None


def serialize_mongo_id(document: dict[str, Any]) -> dict[str, Any]:
    if "_id" in document and isinstance(document["_id"], ObjectId):
        document["id"] = str(document["_id"])
        del document["_id"]
    return document


class GeoPoint(MongoModel):
    type: str = "Point"
    coordinates: list[float] = Field(..., min_length=2, max_length=2)
