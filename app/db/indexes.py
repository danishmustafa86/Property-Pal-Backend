from pymongo import ASCENDING, DESCENDING, GEOSPHERE, TEXT

from app.db.mongodb import get_database


async def create_indexes() -> None:
    db = get_database()
    properties = db["properties"]
    users = db["users"]

    await properties.create_index([("geo_point", GEOSPHERE)], name="geo_point_2dsphere")
    await properties.create_index(
        [("title", TEXT), ("description", TEXT), ("location", TEXT)],
        name="properties_text_idx",
    )
    await properties.create_index(
        [
            ("purpose", ASCENDING),
            ("property_type", ASCENDING),
            ("city", ASCENDING),
            ("price", ASCENDING),
            ("updated_at", DESCENDING),
        ],
        name="search_compound_idx",
    )
    await properties.create_index([("owner_user_id", ASCENDING)], name="owner_idx")
    await properties.create_index([("agent_id", ASCENDING)], name="agent_idx")
    await properties.create_index([("listing_status", ASCENDING)], name="status_idx")

    await users.create_index([("clerk_user_id", ASCENDING)], name="clerk_user_id_unique", unique=True)
    await users.create_index([("email", ASCENDING)], name="email_idx")
