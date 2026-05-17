from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Real Estate Intelligence Backend"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"

    mongodb_uri: str = Field(default="mongodb://localhost:27017")
    # Optional: Atlas "Standard connection string" (mongodb://host:27017,...) when srv DNS is blocked.
    mongodb_uri_standard: str | None = None
    mongodb_db_name: str = "real_estate"
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173"

    clerk_issuer: str = ""
    clerk_jwks_url: AnyHttpUrl | None = None
    clerk_audience: str | None = None
    clerk_secret_key: str = ""

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    google_maps_api_key: str | None = None
    default_page_size: int = 20
    max_page_size: int = 100

    openai_api_key: str | None = None
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1

    @field_validator("clerk_jwks_url", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
