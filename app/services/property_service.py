from fastapi import HTTPException, status

from app.repositories.properties import PropertyRepository
from app.schemas.common import serialize_mongo_id
from app.schemas.property import PropertyCreate, PropertyUpdate
from app.utils.area import sqft_to_marla, to_sqft


class PropertyService:
    def __init__(self) -> None:
        self.repo = PropertyRepository()

    @staticmethod
    def _enrich_payload(payload: dict) -> dict:
        area = payload["area"]
        area_sqft = to_sqft(area["value"], area["unit"])
        payload["area"]["value_sqft_normalized"] = area_sqft
        payload["geo_point"] = {"type": "Point", "coordinates": [payload["longitude"], payload["latitude"]]}
        payload["price_per_marla"] = round(payload["price"] / max(sqft_to_marla(area_sqft), 1), 2)
        payload["market_segment"] = "budget" if payload["price"] < 10_000_000 else "mid" if payload["price"] < 40_000_000 else "premium"
        payload["completeness_score"] = PropertyService._calculate_completeness(payload)
        payload["quality_score"] = payload["completeness_score"]
        return payload

    @staticmethod
    def _calculate_completeness(payload: dict) -> float:
        fields = ["title", "description", "price", "city", "location", "images", "owner_name", "phone", "email"]
        score = sum(1 for field in fields if payload.get(field))
        return round((score / len(fields)) * 100, 2)

    async def create(self, user: dict, data: PropertyCreate) -> dict:
        if user["role"] not in {"agent", "admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only agents can create listings.")
        payload = self._enrich_payload(data.model_dump())
        payload["listing_status"] = "active"
        payload["agent_id"] = user.get("agent_profile_id") or None
        created = await self.repo.create(owner_user_id=user["id"], payload=payload)
        return serialize_mongo_id(created)

    async def get(self, property_id: str) -> dict:
        prop = await self.repo.get_by_id(property_id)
        if not prop:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found.")
        return serialize_mongo_id(prop)

    async def list_for_owner(self, user: dict) -> list[dict]:
        rows = await self.repo.list_for_owner(owner_user_id=user["id"])
        return [serialize_mongo_id(r) for r in rows]

    async def update(self, user: dict, property_id: str, data: PropertyUpdate) -> dict:
        current = await self.repo.get_by_id(property_id)
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found.")
        if str(current["owner_user_id"]) != user["id"] and user["role"] != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to update this listing.")

        payload = data.model_dump(exclude_none=True)
        if "area" in payload or "price" in payload or "latitude" in payload or "longitude" in payload:
            merged = {**current, **payload}
            payload = self._enrich_payload(merged)
        updated = await self.repo.update_property(property_id, payload)
        return serialize_mongo_id(updated)

    async def delete(self, user: dict, property_id: str) -> bool:
        return await self.repo.delete_property(property_id=property_id, owner_user_id=user["id"])

    async def publish(self, user: dict, property_id: str, listing_status: str) -> dict:
        current = await self.repo.get_by_id(property_id)
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found.")
        if str(current["owner_user_id"]) != user["id"] and user["role"] != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to publish this listing.")
        updated = await self.repo.update_property(property_id, {"listing_status": listing_status})
        return serialize_mongo_id(updated)
