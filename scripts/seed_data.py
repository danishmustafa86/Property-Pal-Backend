import argparse
import asyncio
import random
from datetime import datetime, timezone

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.utils.area import sqft_to_marla, to_sqft

# Exact coordinates for every neighbourhood — pins stay inside the actual area
# with a tiny ±0.003° (~300 m) random spread so they don't stack.
NEIGHBOURHOOD_COORDS: dict[tuple[str, str], tuple[float, float]] = {
    # Lahore
    ("Lahore", "DHA Phase 6"):    (31.4622, 74.3740),
    ("Lahore", "DHA Phase 8"):    (31.4370, 74.3620),
    ("Lahore", "Bahria Town"):    (31.3626, 74.1748),
    ("Lahore", "Johar Town"):     (31.4696, 74.2728),
    ("Lahore", "Wapda Town"):     (31.4444, 74.2651),
    ("Lahore", "Model Town"):     (31.5031, 74.3323),
    # Karachi
    ("Karachi", "Clifton"):           (24.8098, 67.0366),
    ("Karachi", "Gulshan-e-Iqbal"):   (24.9268, 67.0942),
    ("Karachi", "Scheme 33"):         (24.9543, 67.1285),
    ("Karachi", "North Nazimabad"):   (24.9400, 67.0454),
    ("Karachi", "DHA Karachi"):       (24.7978, 67.0534),
    ("Karachi", "PECHS"):             (24.8603, 67.0619),
    # Islamabad
    ("Islamabad", "F-10"):          (33.7050, 73.0289),
    ("Islamabad", "F-11"):          (33.7195, 73.0150),
    ("Islamabad", "G-13"):          (33.6596, 73.0175),
    ("Islamabad", "G-11"):          (33.6705, 73.0311),
    ("Islamabad", "B-17"):          (33.6408, 72.9120),
    ("Islamabad", "DHA Islamabad"): (33.5400, 73.1100),
    # Rawalpindi
    ("Rawalpindi", "Bahria Town"):      (33.4836, 73.0479),
    ("Rawalpindi", "PWD"):              (33.6480, 73.1027),
    ("Rawalpindi", "Adyala Road"):      (33.5416, 73.0073),
    ("Rawalpindi", "Saddar"):           (33.6007, 73.0679),
    ("Rawalpindi", "Chaklala Scheme"):  (33.6137, 73.1037),
    ("Rawalpindi", "DHA Phase 2"):      (33.5300, 73.1250),
    # Faisalabad
    ("Faisalabad", "Canal Road"):           (31.4268, 73.0882),
    ("Faisalabad", "Madina Town"):          (31.4387, 73.1039),
    ("Faisalabad", "Peoples Colony"):       (31.4451, 73.1011),
    ("Faisalabad", "Satiana Road"):         (31.4634, 73.1723),
    ("Faisalabad", "Eden Valley"):          (31.4623, 73.0970),
    ("Faisalabad", "Wapda City"):           (31.4297, 73.1278),
    ("Faisalabad", "Susan Road"):           (31.4544, 73.1103),
    ("Faisalabad", "D Ground"):             (31.4148, 73.0902),
    ("Faisalabad", "Jinnah Colony"):        (31.4046, 73.0967),
    ("Faisalabad", "Ghulam Muhammad Abad"): (31.4202, 73.1298),
    ("Faisalabad", "Samanabad"):            (31.4574, 73.0750),
    ("Faisalabad", "Gulberg"):              (31.4338, 73.1060),
    ("Faisalabad", "Millat Town"):          (31.4774, 73.0901),
    ("Faisalabad", "Jaranwala Road"):       (31.4819, 73.2121),
    ("Faisalabad", "Chenab Gardens"):       (31.4005, 73.1002),
    ("Faisalabad", "Abdullah Pur"):         (31.4110, 73.0998),
    ("Faisalabad", "Kotwali Road"):         (31.4189, 73.0950),
    ("Faisalabad", "Sargodha Road"):        (31.4680, 73.0818),
    ("Faisalabad", "Nishatabad"):           (31.4305, 73.1506),
    ("Faisalabad", "Kohinoor City"):        (31.4423, 73.1623),
    ("Faisalabad", "Civil Lines"):          (31.4273, 73.1253),
    ("Faisalabad", "Jhang Road"):           (31.4158, 73.0702),
    ("Faisalabad", "Samundri Road"):        (31.4140, 73.0720),
    ("Faisalabad", "Lyallpur Town"):        (31.4598, 73.1022),
}

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
        "locations": [
            "Canal Road",
            "Madina Town",
            "Peoples Colony",
            "Satiana Road",
            "Eden Valley",
            "Wapda City",
            "Susan Road",
            "D Ground",
            "Jinnah Colony",
            "Ghulam Muhammad Abad",
            "Samanabad",
            "Gulberg",
            "Millat Town",
            "Jaranwala Road",
            "Chenab Gardens",
            "Abdullah Pur",
            "Kotwali Road",
            "Sargodha Road",
            "Nishatabad",
            "Kohinoor City",
            "Civil Lines",
            "Jhang Road",
            "Samundri Road",
            "Lyallpur Town",
        ],
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


def _motor_kwargs() -> dict:
    uri = settings.mongodb_uri.lower()
    if "mongodb+srv://" in uri or "tls=true" in uri:
        kwargs: dict = {"tlsCAFile": certifi.where()}
        if settings.environment == "development":
            kwargs["tlsAllowInvalidCertificates"] = True
        return kwargs
    return {}


def build_house(i: int, *, city: str | None = None, owner_user_id: str = "seed-user") -> dict:
    city = city or random.choice(list(CITY_POOLS.keys()))
    pool = CITY_POOLS[city]
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
    lat_base, lng_base = NEIGHBOURHOOD_COORDS.get((city, location), pool["base"])
    lat = lat_base + random.uniform(-0.003, 0.003)
    lng = lng_base + random.uniform(-0.003, 0.003)
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
        "owner_user_id": owner_user_id,
        "created_at": now,
        "updated_at": now,
    }


def build_apartment(i: int, *, city: str | None = None, owner_user_id: str = "seed-user") -> dict:
    city = city or random.choice(list(CITY_POOLS.keys()))
    pool = CITY_POOLS[city]
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
    lat_base, lng_base = NEIGHBOURHOOD_COORDS.get((city, location), pool["base"])
    lat = lat_base + random.uniform(-0.003, 0.003)
    lng = lng_base + random.uniform(-0.003, 0.003)
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
        "owner_user_id": owner_user_id,
        "created_at": now,
        "updated_at": now,
    }


async def seed(
    total: int,
    clear_old_seed: bool,
    *,
    city: str | None = None,
    houses_only: bool = False,
    start_index: int = 0,
    owner_user_id: str = "seed-user",
) -> None:
    client = AsyncIOMotorClient(settings.mongodb_uri, **_motor_kwargs())
    db = client[settings.mongodb_db_name]
    properties = db["properties"]

    if clear_old_seed:
        deleted = await properties.delete_many({"owner_user_id": owner_user_id})
        print(f"Deleted {deleted.deleted_count} old seed properties (owner_user_id={owner_user_id!r}).")

    house_count = total
    apt_count = 0 if houses_only else max(total // 2, 10)
    docs = [
        build_house(start_index + i, city=city, owner_user_id=owner_user_id)
        for i in range(house_count)
    ]
    if apt_count:
        docs += [
            build_apartment(start_index + i, city=city, owner_user_id=owner_user_id)
            for i in range(apt_count)
        ]
    result = await properties.insert_many(docs)
    city_note = f" in {city}" if city else ""
    print(
        f"Inserted {len(result.inserted_ids)} seed listings{city_note} "
        f"({house_count} houses, {apt_count} apartments)."
    )
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
    parser.add_argument(
        "--city",
        type=str,
        default=None,
        choices=list(CITY_POOLS.keys()),
        help="Restrict all listings to one city (e.g. Faisalabad).",
    )
    parser.add_argument(
        "--houses-only",
        action="store_true",
        help="Insert houses only (no apartments).",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Offset for owner phone/email numbering (use when appending seed data).",
    )
    parser.add_argument(
        "--owner-user-id",
        type=str,
        default=None,
        help="owner_user_id tag for seeded docs (default: seed-user, or seed-user-<city>).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    random.seed(args.seed)
    owner_user_id = args.owner_user_id or (
        f"seed-user-{args.city.lower().replace(' ', '-')}" if args.city else "seed-user"
    )
    asyncio.run(
        seed(
            total=max(args.count, 1),
            clear_old_seed=args.clear_old_seed,
            city=args.city,
            houses_only=args.houses_only,
            start_index=max(args.start_index, 0),
            owner_user_id=owner_user_id,
        )
    )
