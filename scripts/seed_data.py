import argparse
import asyncio
import random
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.utils.area import sqft_to_marla, to_sqft

CITY_POOLS = {
    "Lahore": {
        "base": (31.5204, 74.3587),
        "locations": ["DHA Phase 6", "DHA Phase 8", "Bahria Town", "Johar Town", "Wapda Town", "Model Town"],
    },
    "Karachi": {
        "base": (24.8607, 67.0011),
        "locations": ["Clifton", "Gulshan-e-Iqbal", "Scheme 33", "North Nazimabad", "DHA Karachi", "PECHS"],
    },
    "Islamabad": {
        "base": (33.6844, 73.0479),
        "locations": ["F-10", "F-11", "G-13", "G-11", "B-17", "DHA Islamabad"],
    },
    "Rawalpindi": {
        "base": (33.5651, 73.0169),
        "locations": ["Bahria Town", "PWD", "Adyala Road", "Saddar", "Chaklala Scheme", "DHA Phase 2"],
    },
    "Faisalabad": {
        "base": (31.4504, 73.1350),
        "locations": ["Canal Road", "Madina Town", "Peoples Colony", "Satiana Road", "Eden Valley", "Wapda City"],
    },
}

TITLE_PREFIX = [
    "Executive",
    "Modern",
    "Corner",
    "Family",
    "Luxury",
    "Prime",
    "Spacious",
    "Brand New",
    "Affordable",
]


def build_house(i: int) -> dict:
    city = random.choice(list(CITY_POOLS.keys()))
    pool = CITY_POOLS[city]
    lat_base, lng_base = pool["base"]
    location = random.choice(pool["locations"])
    purpose = random.choices(["buy", "rent"], weights=[75, 25])[0]
    marlas = random.choice([3, 5, 7, 10, 12, 15, 20])

    if purpose == "buy":
        # Approx Pakistani buy ranges by marla.
        price_million = {
            3: (8, 14),
            5: (16, 35),
            7: (24, 48),
            10: (38, 75),
            12: (45, 90),
            15: (60, 130),
            20: (90, 220),
        }[marlas]
        price = random.randint(price_million[0], price_million[1]) * 1_000_000
    else:
        # Monthly rent ranges.
        rent_thousand = {
            3: (35, 70),
            5: (60, 130),
            7: (90, 180),
            10: (120, 280),
            12: (170, 360),
            15: (220, 500),
            20: (300, 700),
        }[marlas]
        price = random.randint(rent_thousand[0], rent_thousand[1]) * 1_000

    bedrooms = random.randint(2, min(8, max(3, int(sqft_to_marla(to_sqft(marlas, "marla")) // 2 + 2))))
    bathrooms = max(2, bedrooms - random.choice([0, 1]))
    rooms = bedrooms + random.randint(1, 3)
    kitchens = 1 if marlas <= 5 else random.choice([1, 2])
    stories = random.choice([1, 2, 3]) if marlas >= 7 else random.choice([1, 2])
    year = random.randint(2012, 2025)
    lat = lat_base + random.uniform(-0.06, 0.06)
    lng = lng_base + random.uniform(-0.08, 0.08)
    now = datetime.now(timezone.utc)

    title = f"{marlas} Marla {random.choice(TITLE_PREFIX)} House {location}"
    area_sqft = to_sqft(marlas, "marla")
    price_per_marla = round(price / max(marlas, 1), 2)
    market_segment = "budget" if price < 10_000_000 else "mid" if price < 40_000_000 else "premium"

    return {
        "title": title,
        "description": (
            f"{title} in {location}, {city}. "
            f"{bedrooms} bed, {bathrooms} bath, parking and nearby facilities. Ideal for {purpose}."
        ),
        "price": price,
        "purpose": purpose,
        "property_type": "house",
        "city": city,
        "location": location,
        "latitude": round(lat, 6),
        "longitude": round(lng, 6),
        "geo_point": {"type": "Point", "coordinates": [round(lng, 6), round(lat, 6)]},
        "area": {"value": marlas, "unit": "marla", "value_sqft_normalized": area_sqft},
        "number_of_rooms": rooms,
        "number_of_bedrooms": bedrooms,
        "number_of_bathrooms": bathrooms,
        "kitchens": kitchens,
        "drawing_rooms": random.choice([1, 1, 2]),
        "stories": stories,
        "garage": random.choice([True, True, False]),
        "construction_year": year,
        "new_construction": year >= 2023,
        "nearby_schools": ["Model School", "City Grammar"],
        "nearby_mosques": ["Jamia Mosque"],
        "nearby_markets": ["Main Market", "Commercial Area"],
        "nearby_restaurants": ["Food Street", "Local BBQ"],
        "environmental_risks": [],
        "owner_name": f"Seed Owner {i + 1}",
        "phone": f"+92-300-{1000000 + i}",
        "email": f"seed_owner_{i + 1}@example.com",
        "agent_id": None,
        "images": [],
        "society": location,
        "sub_area": location,
        "province": "Punjab" if city in {"Lahore", "Rawalpindi", "Faisalabad"} else ("Sindh" if city == "Karachi" else "Islamabad"),
        "listing_status": "active",
        "verification_status": "verified_owner",
        "quality_score": round(random.uniform(80, 96), 2),
        "completeness_score": round(random.uniform(86, 99), 2),
        "views_count": random.randint(0, 150),
        "saves_count": random.randint(0, 40),
        "shares_count": random.randint(0, 12),
        "inquiry_count": random.randint(0, 20),
        "price_per_marla": price_per_marla,
        "market_segment": market_segment,
        "owner_user_id": "seed-user",
        "created_at": now,
        "updated_at": now,
    }


def build_apartment(i: int) -> dict:
    city = random.choice(list(CITY_POOLS.keys()))
    pool = CITY_POOLS[city]
    lat_base, lng_base = pool["base"]
    location = random.choice(pool["locations"])
    purpose = random.choices(["buy", "rent"], weights=[50, 50])[0]
    bedrooms = random.choice([1, 2, 3, 4, 5])

    if purpose == "buy":
        price_million = {1: (4, 10), 2: (8, 18), 3: (14, 30), 4: (22, 50), 5: (35, 75)}[bedrooms]
        price = random.randint(price_million[0], price_million[1]) * 1_000_000
    else:
        rent_thousand = {1: (25, 55), 2: (40, 90), 3: (65, 150), 4: (100, 220), 5: (160, 350)}[bedrooms]
        price = random.randint(rent_thousand[0], rent_thousand[1]) * 1_000

    bathrooms = max(1, bedrooms - random.choice([0, 1]))
    rooms = bedrooms + random.randint(0, 2)
    marlas = random.choice([3, 5, 7, 10])
    area_sqft = to_sqft(marlas, "marla")
    lat = lat_base + random.uniform(-0.06, 0.06)
    lng = lng_base + random.uniform(-0.08, 0.08)
    now = datetime.now(timezone.utc)
    prefix = random.choice(TITLE_PREFIX)
    title = f"{bedrooms} Bed {prefix} Apartment {location}"
    price_per_marla = round(price / max(marlas, 1), 2)
    market_segment = "budget" if price < 10_000_000 else "mid" if price < 40_000_000 else "premium"

    return {
        "title": title,
        "description": (
            f"{title} in {location}, {city}. "
            f"{bedrooms} bed, {bathrooms} bath, modern amenities. Ideal for {purpose}."
        ),
        "price": price,
        "purpose": purpose,
        "property_type": "apartment",
        "city": city,
        "location": location,
        "latitude": round(lat, 6),
        "longitude": round(lng, 6),
        "geo_point": {"type": "Point", "coordinates": [round(lng, 6), round(lat, 6)]},
        "area": {"value": marlas, "unit": "marla", "value_sqft_normalized": area_sqft},
        "number_of_rooms": rooms,
        "number_of_bedrooms": bedrooms,
        "number_of_bathrooms": bathrooms,
        "kitchens": 1,
        "drawing_rooms": random.choice([0, 1]),
        "stories": 1,
        "garage": random.choice([True, False, False]),
        "construction_year": random.randint(2015, 2025),
        "new_construction": False,
        "nearby_schools": ["Model School", "City Grammar"],
        "nearby_mosques": ["Jamia Mosque"],
        "nearby_markets": ["Main Market", "Commercial Area"],
        "nearby_restaurants": ["Food Street", "Local BBQ"],
        "environmental_risks": [],
        "owner_name": f"Seed Owner Apt {i + 1}",
        "phone": f"+92-301-{2000000 + i}",
        "email": f"seed_apt_{i + 1}@example.com",
        "agent_id": None,
        "images": [],
        "society": location,
        "sub_area": location,
        "province": "Punjab" if city in {"Lahore", "Rawalpindi", "Faisalabad"} else ("Sindh" if city == "Karachi" else "Islamabad"),
        "listing_status": "active",
        "verification_status": "verified_owner",
        "quality_score": round(random.uniform(75, 96), 2),
        "completeness_score": round(random.uniform(80, 99), 2),
        "views_count": random.randint(0, 120),
        "saves_count": random.randint(0, 30),
        "shares_count": random.randint(0, 10),
        "inquiry_count": random.randint(0, 15),
        "price_per_marla": price_per_marla,
        "market_segment": market_segment,
        "owner_user_id": "seed-user",
        "created_at": now,
        "updated_at": now,
    }


async def seed(total: int, clear_old_seed: bool) -> None:
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    properties = db["properties"]

    if clear_old_seed:
        deleted = await properties.delete_many({"owner_user_id": "seed-user"})
        print(f"Deleted {deleted.deleted_count} old seed properties.")

    house_count = total
    apt_count = max(total // 2, 10)
    docs = [build_house(i) for i in range(house_count)]
    docs += [build_apartment(i) for i in range(apt_count)]
    result = await properties.insert_many(docs)
    print(f"Inserted {len(result.inserted_ids)} seed listings ({house_count} houses, {apt_count} apartments).")
    client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed mock house listings for frontend testing.")
    parser.add_argument("--count", type=int, default=50, help="Number of house records to insert.")
    parser.add_argument(
        "--clear-old-seed",
        action="store_true",
        help="Delete previously seeded docs where owner_user_id is 'seed-user' before inserting new ones.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible data.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    random.seed(args.seed)
    asyncio.run(seed(total=max(args.count, 1), clear_old_seed=args.clear_old_seed))
