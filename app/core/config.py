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
    mongodb_db_name: str = "real_estate"
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173"

    clerk_issuer: str = ""
    clerk_jwks_url: AnyHttpUrl | None = None
    clerk_audience: str | None = None
    clerk_secret_key: str = ""

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    openai_api_key: str | None = None
    openai_api_key_fallback: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 800
    agent_enable_write_tools: bool = True
    agent_require_write_confirmation: bool = True
    agent_summary_trigger_messages: int = 12
    agent_summary_keep_last_messages: int = 6
    agent_summary_max_tokens: int = 256
    default_page_size: int = 20
    max_page_size: int = 100

    # Investment analyst pipeline
    data_dir: str | None = None
    tavily_api_key: str | None = None
    investment_forecast_horizon_months: int = 12

    @field_validator("clerk_jwks_url", "llm_base_url", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
