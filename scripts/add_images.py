"""Add curated house/property images to seed listings in MongoDB."""
import asyncio
import random

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

HOUSE_IMAGES = [
    "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600596542815-ffad4c1539a6?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1572120360610-d971b9d7767c?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1605276374104-dee2a0ed3cd6?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1494526585095-c41746248156?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600585154526-990dced4db0d?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1602941525421-8f8b81d3eddb?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1560185007-cde436f6a4d0?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1562078809-c5391ebb3205?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600573472592-401b489a3cdc?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1599427303058-f04cbcf4756f?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600585152220-90363fe7e115?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1613977257363-707ba9348227?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600563438938-a9a27216b4f5?w=800&h=600&fit=crop&q=80",
]

INTERIOR_IMAGES = [
    "https://images.unsplash.com/photo-1600210491892-03d54c0aaf87?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600607687644-c7171b42498f?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600566752355-35792bedcfea?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600585153490-76fb20a32601?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600121848594-d8644e57abab?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1616137466211-f736a1f58b8a?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600607688969-a5bfcd646154?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1600566752547-33fc2c71d42c?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800&h=600&fit=crop&q=80",
    "https://images.unsplash.com/photo-1560448075-cbc16bb4af8e?w=800&h=600&fit=crop&q=80",
]


async def main():
    random.seed(42)
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    col = db["properties"]

    cursor = col.find({"images": {"$size": 0}})
    docs = await cursor.to_list(length=200)

    if not docs:
        print("No properties with empty images found.")
        client.close()
        return

    updated = 0
    shuffled_houses = HOUSE_IMAGES[:]
    random.shuffle(shuffled_houses)

    for i, doc in enumerate(docs):
        exterior = shuffled_houses[i % len(shuffled_houses)]
        interior1 = random.choice(INTERIOR_IMAGES)
        interior2 = random.choice([img for img in INTERIOR_IMAGES if img != interior1])
        extra_exterior = random.choice([img for img in HOUSE_IMAGES if img != exterior])

        images = [exterior, interior1, interior2, extra_exterior]

        await col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"images": images}},
        )
        updated += 1

    print(f"Updated {updated} properties with images.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
