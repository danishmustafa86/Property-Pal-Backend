from fastapi import APIRouter, Depends

from app.auth.dependencies import current_user, current_user_optional
from app.repositories.queries import SavedSearchRepository
from app.schemas.chat import ChatQueryRequest
from app.schemas.search import IntentSearchRequest, SearchRequest
from app.services.chat_service import ChatService
from app.services.search_service import SearchService

router = APIRouter()
search_service = SearchService()
chat_service = ChatService()
saved_repo = SavedSearchRepository()


@router.get("/")
async def search_properties(
    city: str | None = None,
    purpose: str | None = None,
    property_type: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_marlas: float | None = None,
    max_marlas: float | None = None,
    rooms: int | None = None,
    bathrooms: int | None = None,
    new_construction: bool | None = None,
    garage: bool | None = None,
    min_construction_year: int | None = None,
    max_construction_year: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float | None = None,
    keyword: str | None = None,
    page_size: int = 20,
    cursor: str | None = None,
    _: dict | None = Depends(current_user_optional),
):
    request = SearchRequest(
        city=city,
        purpose=purpose,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price,
        min_marlas=min_marlas,
        max_marlas=max_marlas,
        rooms=rooms,
        bathrooms=bathrooms,
        new_construction=new_construction,
        garage=garage,
        min_construction_year=min_construction_year,
        max_construction_year=max_construction_year,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        keyword=keyword,
        page_size=page_size,
        cursor=cursor,
    )
    return await search_service.search(request)


@router.post("/intent")
async def search_intent(payload: IntentSearchRequest, user: dict = Depends(current_user)):
    return await chat_service.query(user, payload=ChatQueryRequest(query=payload.query, limit=payload.page_size))


@router.post("/save")
async def save_search(request: SearchRequest, user: dict = Depends(current_user)):
    saved = await saved_repo.save(user_id=user["id"], filters=request.model_dump(exclude_none=True))
    saved["id"] = str(saved["_id"])
    del saved["_id"]
    return saved


@router.get("/saved")
async def list_saved_searches(user: dict = Depends(current_user)):
    docs = await saved_repo.list_saved(user["id"])
    for doc in docs:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return docs
