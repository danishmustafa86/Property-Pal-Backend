"""FastAPI application: property APIs plus LangGraph **Advanced Investment Analyst** (see ``app.agents.graph``)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middlewares
from app.db.indexes import create_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.observability.logging import configure_logging
from app.routes import agents, chat, health, map_properties, properties, search, uploads, users

_startup_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect_to_mongo()
    try:
        await create_indexes()
    except Exception as exc:
        _startup_logger.warning("Index creation skipped (non-fatal): %s", exc)
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
configure_logging()
register_exception_handlers(app)
register_middlewares(app)
allowed_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(users.router, prefix="/me", tags=["users"])
app.include_router(properties.router, prefix="/properties", tags=["properties"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(map_properties.router, prefix="/map-properties", tags=["map"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
