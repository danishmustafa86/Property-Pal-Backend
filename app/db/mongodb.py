import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def _motor_client_kwargs() -> dict:
    """Atlas and other TLS MongoDB URLs need a CA bundle; Windows Python often lacks one in ssl.

    tlsAllowInvalidCertificates=True in dev works around TLSV1_ALERT_INTERNAL_ERROR
    caused by Python 3.12 + Windows OpenSSL TLS handshake quirks with Atlas.
    """
    uri = settings.mongodb_uri.lower()
    if "mongodb+srv://" in uri or "tls=true" in uri:
        kwargs: dict = {"tlsCAFile": certifi.where()}
        if settings.environment == "development":
            kwargs["tlsAllowInvalidCertificates"] = True
        return kwargs
    return {}


async def connect_to_mongo() -> None:
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri, **_motor_client_kwargs())
        _db = _client[settings.mongodb_db_name]


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
