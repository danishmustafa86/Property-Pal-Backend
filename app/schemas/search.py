from typing import Literal

from pydantic import Field

from app.schemas.common import MongoModel, PaginatedResponse
from app.schemas.property import PropertyOut


class SearchFilters(MongoModel):
    city: str | None = None
    purpose: Literal["rent", "buy"] | None = None
    property_type: str | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    min_marlas: float | None = Field(default=None, ge=0)
    max_marlas: float | None = Field(default=None, ge=0)
    rooms: int | None = Field(default=None, ge=0)
    max_rooms: int | None = Field(default=None, ge=0)
    total_rooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    furnished: bool | None = None
    new_construction: bool | None = None
    garage: bool | None = None
    min_construction_year: int | None = None
    max_construction_year: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = Field(default=None, gt=0)
    keyword: str | None = None
    # Google Places proximity filter
    near_place_type: str | None = None          # hospital | mosque | school | restaurant | market | park | pharmacy
    near_place_types: list[str] | None = None   # require all listed types when set
    near_place_radius_km: float | None = Field(default=2.0, gt=0, le=10)


class SearchRequest(SearchFilters):
    page_size: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class IntentSearchRequest(MongoModel):
    query: str
    page_size: int = Field(default=20, ge=1, le=100)


class SearchResponse(PaginatedResponse):
    items: list[PropertyOut]


class MapViewportQuery(MongoModel):
    min_lat: float = Field(..., ge=-90, le=90)
    min_lng: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)
    max_lng: float = Field(..., ge=-180, le=180)
    purpose: Literal["rent", "buy"] | None = None
    property_type: str | None = None


class MapMarker(MongoModel):
    id: str
    lat: float
    lng: float
    price: int
    purpose: str
    property_type: str
    thumbnail: str | None = None
    score: float
