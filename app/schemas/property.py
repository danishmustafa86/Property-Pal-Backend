from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import GeoPoint, MongoModel


class NearbyPlace(BaseModel):
    """Structured place entry returned by Google Places API."""
    place_id: str = ""
    name: str
    place_type: str   # hospital | mosque | school | restaurant | market | pharmacy | park | bank | gym
    distance_meters: float | None = None
    rating: float | None = None
    address: str | None = None
    open_now: bool | None = None
    latitude: float | None = None
    longitude: float | None = None

Purpose = Literal["rent", "buy"]
PropertyType = Literal["house", "shop", "plot", "apartment", "office", "warehouse", "farmhouse"]
AreaUnit = Literal["marla", "kanal", "sqft", "sqyd"]
ListingStatus = Literal["draft", "active", "pending", "sold", "rented", "archived"]
VerificationStatus = Literal["unverified", "verified_agent", "verified_owner"]


class Area(MongoModel):
    value: float = Field(..., gt=0)
    unit: AreaUnit
    value_sqft_normalized: float = Field(..., gt=0)


class EnvironmentalRisk(MongoModel):
    type: Literal["flood", "pollution", "noise", "other"]
    score: float = Field(ge=0, le=1)
    source: str


class PropertyBase(MongoModel):
    title: str = Field(min_length=5, max_length=180)
    description: str = Field(min_length=20, max_length=5000)
    price: int = Field(..., ge=1)
    purpose: Purpose
    property_type: PropertyType
    city: str
    location: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    area: Area
    number_of_rooms: int = Field(0, ge=0)
    number_of_bedrooms: int = Field(0, ge=0)
    number_of_bathrooms: int = Field(0, ge=0)
    kitchens: int = Field(0, ge=0)
    drawing_rooms: int = Field(0, ge=0)
    stories: int = Field(0, ge=0)
    garage: bool = False
    construction_year: int | None = None
    new_construction: bool = False

    nearby_schools: list[str] = []
    nearby_mosques: list[str] = []
    nearby_markets: list[str] = []
    nearby_restaurants: list[str] = []
    nearby_places: list[NearbyPlace] = []   # structured Google Places data (replaces static strings)
    environmental_risks: list[EnvironmentalRisk] = []

    owner_name: str
    phone: str
    email: EmailStr
    agent_id: str | None = None

    images: list[str] = []
    society: str | None = None
    sub_area: str | None = None
    province: str | None = None
    listing_status: ListingStatus = "draft"
    verification_status: VerificationStatus = "unverified"
    quality_score: float = Field(default=0, ge=0, le=100)
    completeness_score: float = Field(default=0, ge=0, le=100)
    views_count: int = Field(default=0, ge=0)
    saves_count: int = Field(default=0, ge=0)
    shares_count: int = Field(default=0, ge=0)
    inquiry_count: int = Field(default=0, ge=0)


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(MongoModel):
    title: str | None = None
    description: str | None = None
    price: int | None = Field(default=None, ge=1)
    purpose: Purpose | None = None
    property_type: PropertyType | None = None
    city: str | None = None
    location: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    area: Area | None = None
    number_of_rooms: int | None = Field(default=None, ge=0)
    number_of_bedrooms: int | None = Field(default=None, ge=0)
    number_of_bathrooms: int | None = Field(default=None, ge=0)
    kitchens: int | None = Field(default=None, ge=0)
    drawing_rooms: int | None = Field(default=None, ge=0)
    stories: int | None = Field(default=None, ge=0)
    garage: bool | None = None
    construction_year: int | None = None
    new_construction: bool | None = None
    nearby_schools: list[str] | None = None
    nearby_mosques: list[str] | None = None
    nearby_markets: list[str] | None = None
    nearby_restaurants: list[str] | None = None
    environmental_risks: list[EnvironmentalRisk] | None = None
    owner_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    agent_id: str | None = None
    images: list[str] | None = None
    society: str | None = None
    sub_area: str | None = None
    province: str | None = None
    listing_status: ListingStatus | None = None
    verification_status: VerificationStatus | None = None


class PropertyOut(PropertyBase):
    id: str
    owner_user_id: str
    geo_point: GeoPoint
    price_per_marla: float | None = None
    market_segment: Literal["budget", "mid", "premium"] | None = None
    days_on_market: int = 0
    spam_flag: bool = False
    fraud_score: float = Field(default=0, ge=0, le=1)
    created_at: datetime
    updated_at: datetime


class PublishRequest(MongoModel):
    listing_status: Literal["active", "archived"]
