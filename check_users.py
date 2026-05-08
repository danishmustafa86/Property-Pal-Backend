import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


async def show():
    c = AsyncIOMotorClient(settings.mongodb_uri)
    db = c[settings.mongodb_db_name]
    async for u in db["users"].find():
        uid = u["_id"]
        name = u.get("full_name", "?")
        email = u.get("email", "?")
        role = u.get("role", "?")
        print(f"ID={uid} | name={name} | email={email} | role={role}")
    c.close()


asyncio.run(show())
