from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import current_user, current_user_optional
from app.schemas.property import PropertyCreate, PropertyUpdate, PublishRequest
from app.services.property_service import PropertyService

router = APIRouter()
service = PropertyService()


@router.post("/")
async def create_property(payload: PropertyCreate, user: dict = Depends(current_user)):
    return await service.create(user, payload)


@router.get("/")
async def list_my_properties(user: dict = Depends(current_user)):
    return await service.list_for_owner(user)


@router.get("/{property_id}")
async def get_property(property_id: str, _: dict | None = Depends(current_user_optional)):
    return await service.get(property_id)


@router.put("/{property_id}")
async def update_property(property_id: str, payload: PropertyUpdate, user: dict = Depends(current_user)):
    return await service.update(user, property_id, payload)


@router.delete("/{property_id}")
async def delete_property(property_id: str, user: dict = Depends(current_user)):
    deleted = await service.delete(user, property_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found.")
    return {"deleted": True}


@router.post("/{property_id}/publish")
async def publish_property(property_id: str, payload: PublishRequest, user: dict = Depends(current_user)):
    return await service.publish(user, property_id, payload.listing_status)
