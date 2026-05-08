from fastapi import APIRouter, Depends

from app.auth.dependencies import current_user_optional
from app.schemas.search import MapViewportQuery
from app.services.map_service import MapService

router = APIRouter()
service = MapService()


@router.get("/")
async def map_properties(
    min_lat: float,
    min_lng: float,
    max_lat: float,
    max_lng: float,
    purpose: str | None = None,
    property_type: str | None = None,
    _: dict | None = Depends(current_user_optional),
):
    payload = MapViewportQuery(
        min_lat=min_lat,
        min_lng=min_lng,
        max_lat=max_lat,
        max_lng=max_lng,
        purpose=purpose,
        property_type=property_type,
    )
    return await service.search_in_viewport(payload)
