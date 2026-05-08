"""Ping MongoDB and summarize collections (run from repo: cd backend && python scripts/check_db.py)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def main() -> None:
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient

    from app.core.config import settings

    uri = settings.mongodb_uri
    uri_lower = uri.lower()
    kwargs: dict = {}
    if "mongodb+srv://" in uri_lower or "tls=true" in uri_lower:
        kwargs["tlsCAFile"] = certifi.where()

    print(f"Connecting to database name: {settings.mongodb_db_name!r}")
    print(f"URI scheme: {uri.split('://', 1)[0] if '://' in uri else '???'}://...")

    client = AsyncIOMotorClient(uri, **kwargs)
    try:
        await client.admin.command("ping")
        print("OK: admin ping succeeded.\n")

        db = client[settings.mongodb_db_name]
        props = db["properties"]

        total = await props.count_documents({})
        by_status: dict[str, int] = {}
        async for doc in props.aggregate([{"$group": {"_id": "$listing_status", "n": {"$sum": 1}}}]):
            key = str(doc["_id"] if doc["_id"] is not None else "null")
            by_status[key] = doc["n"]

        print(f"Collection 'properties': {total} document(s)")
        if by_status:
            print("  by listing_status:")
            for k, n in sorted(by_status.items(), key=lambda x: (-x[1], x[0])):
                print(f"    {k}: {n}")
        else:
            print("  (no documents)")

        active = by_status.get("active", 0)
        if total > 0 and active == 0:
            print(
                "\nNote: Public search & homepage only show listing_status == 'active'. "
                "Drafts do not appear until you publish a listing in the dashboard."
            )

        for name in ("users", "agents", "saved_searches"):
            n = await db[name].count_documents({})
            print(f"Collection {name!r}: {n} document(s)")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
