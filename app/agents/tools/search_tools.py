from __future__ import annotations

from pydantic import BaseModel, Field
from langchain_core.tools import tool

from app.schemas.search import SearchRequest
from app.services.search_service import SearchService


class SearchPropertiesInput(BaseModel):
    city: str | None = None
    purpose: str | None = None
    property_type: str | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    min_marlas: float | None = Field(default=None, ge=0)
    max_marlas: float | None = Field(default=None, ge=0)
    rooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    keyword: str | None = None
    page_size: int = Field(default=10, ge=1, le=50)
    cursor: str | None = None


def build_search_tools() -> list:
    service = SearchService()

    @tool("search_properties", args_schema=SearchPropertiesInput)
    async def search_properties(**kwargs) -> dict:
        """Search active property listings with flexible filters and pagination."""
        input_data = SearchPropertiesInput(**kwargs)
        request = SearchRequest(**input_data.model_dump(exclude_none=True))
        response = await service.search(request)
        return {
            **response,
            "filters": request.model_dump(exclude_none=True),
        }

    return [search_properties]
