import logging
from urllib.parse import quote_plus, urlparse

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

_MONGO_TIMEOUT_MS = 8_000
_PUBLIC_DNS = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]


def _public_dns_resolver():
    import dns.resolver

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = _PUBLIC_DNS
    resolver.lifetime = 5.0
    return resolver


def _expand_srv_uri(srv_uri: str) -> str | None:
    """Build mongodb:// URI from mongodb+srv:// without TXT lookups (often blocked on campus DNS)."""
    if not srv_uri.lower().startswith("mongodb+srv://"):
        return None

    parsed = urlparse(srv_uri)
    cluster_host = parsed.hostname
    if not cluster_host:
        return None

    try:
        answers = _public_dns_resolver().resolve(f"_mongodb._tcp.{cluster_host}", "SRV")
    except Exception as exc:
        logger.warning("SRV resolve failed for %s: %s", cluster_host, exc)
        return None

    hosts = ",".join(
        f"{str(record.target).rstrip('.')}:27017"
        for record in sorted(answers, key=lambda r: (r.priority, -r.weight))
    )
    if not hosts:
        return None

    db_name = (parsed.path or "").lstrip("/") or settings.mongodb_db_name
    userinfo = ""
    if parsed.username:
        password = parsed.password or ""
        userinfo = f"{quote_plus(parsed.username)}:{quote_plus(password)}@"

    query = "ssl=true&authSource=admin&retryWrites=true&w=majority"
    if parsed.query:
        query = f"{parsed.query}&{query}" if "ssl=" not in parsed.query else parsed.query

    standard = f"mongodb://{userinfo}{hosts}/{db_name}?{query}"
    logger.info("Expanded mongodb+srv:// to standard connection string (no SRV/TXT at connect time)")
    return standard


def _resolve_mongodb_uri() -> str:
    if settings.mongodb_uri_standard and settings.mongodb_uri_standard.strip():
        logger.info("Using MONGODB_URI_STANDARD from environment")
        return settings.mongodb_uri_standard.strip()

    if settings.mongodb_uri.lower().startswith("mongodb+srv://"):
        expanded = _expand_srv_uri(settings.mongodb_uri)
        if expanded:
            return expanded

    return settings.mongodb_uri


def _motor_client_kwargs(uri: str) -> dict:
    """Atlas and other TLS MongoDB URLs need a CA bundle; Windows Python often lacks one in ssl."""
    lower = uri.lower()
    if lower.startswith("mongodb+srv://") or "tls=true" in lower or "ssl=true" in lower:
        kwargs: dict = {"tlsCAFile": certifi.where()}
        if settings.environment == "development":
            kwargs["tlsAllowInvalidCertificates"] = True
        return kwargs
    return {}


async def connect_to_mongo() -> None:
    global _client, _db
    if _client is None:
        uri = _resolve_mongodb_uri()
        _client = AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=_MONGO_TIMEOUT_MS,
            connectTimeoutMS=_MONGO_TIMEOUT_MS,
            **_motor_client_kwargs(uri),
        )
        _db = _client[settings.mongodb_db_name]
        try:
            await _client.admin.command("ping")
            logger.info("MongoDB connected (%s)", settings.mongodb_db_name)
        except Exception as exc:
            logger.error(
                "MongoDB connection failed. Set MONGODB_URI_STANDARD (Atlas standard string) or "
                "MONGODB_URI=mongodb://localhost:27017 for local dev. Error: %s",
                exc,
            )
            raise


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB connection is not initialized.")
    return _db
