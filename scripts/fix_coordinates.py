"""
Fix properties whose coordinates are outside their city's expected bounding box.

Usage:
    cd backend
    python scripts/fix_coordinates.py           # dry-run (no writes)
    python scripts/fix_coordinates.py --apply   # write fixes to MongoDB
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

# Expected bounding box for each city  (lat_min, lat_max, lng_min, lng_max)
CITY_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "Lahore":      (31.20, 31.80, 73.90, 74.70),
    "Karachi":     (24.55, 25.25, 66.65, 67.45),
    "Islamabad":   (33.45, 33.90, 72.70, 73.40),
    "Rawalpindi":  (33.40, 33.80, 72.80, 73.30),
    "Faisalabad":  (31.28, 31.65, 72.85, 73.40),
    "Multan":      (29.90, 30.45, 71.25, 71.85),
    "Peshawar":    (33.80, 34.25, 71.30, 71.80),
    "Gujranwala":  (32.00, 32.40, 74.00, 74.40),
    "Quetta":      (30.00, 30.40, 66.75, 67.25),
}

# Exact (lat, lng) for every neighbourhood used in seed data
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
    ("Faisalabad", "Canal Road"):                    (31.4268, 73.0882),
    ("Faisalabad", "Madina Town"):                   (31.4387, 73.1039),
    ("Faisalabad", "Peoples Colony"):                (31.4451, 73.1011),
    ("Faisalabad", "Satiana Road"):                  (31.4634, 73.1723),
    ("Faisalabad", "Eden Valley"):                   (31.4623, 73.0970),
    ("Faisalabad", "Wapda City"):                    (31.4297, 73.1278),
    ("Faisalabad", "Susan Road"):                    (31.4544, 73.1103),
    ("Faisalabad", "D Ground"):                      (31.4148, 73.0902),
    ("Faisalabad", "Jinnah Colony"):                 (31.4046, 73.0967),
    ("Faisalabad", "Ghulam Muhammad Abad"):          (31.4202, 73.1298),
    ("Faisalabad", "Samanabad"):                     (31.4574, 73.0750),
    ("Faisalabad", "Gulberg"):                       (31.4338, 73.1060),
    ("Faisalabad", "Millat Town"):                   (31.4774, 73.0901),
    ("Faisalabad", "Jaranwala Road"):                (31.4819, 73.2121),
    ("Faisalabad", "Chenab Gardens"):                (31.4005, 73.1002),
    ("Faisalabad", "Abdullah Pur"):                  (31.4110, 73.0998),
    ("Faisalabad", "Kotwali Road"):                  (31.4189, 73.0950),
    ("Faisalabad", "Sargodha Road"):                 (31.4680, 73.0818),
    ("Faisalabad", "Nishatabad"):                    (31.4305, 73.1506),
    ("Faisalabad", "Kohinoor City"):                 (31.4423, 73.1623),
    ("Faisalabad", "Civil Lines"):                   (31.4273, 73.1253),
    ("Faisalabad", "Jhang Road"):                    (31.4158, 73.0702),
    ("Faisalabad", "Samundri Road"):                 (31.4140, 73.0720),
    ("Faisalabad", "City Housing"):                  (31.4050, 73.0810),
    ("Faisalabad", "City Housing, Samundari Road"):  (31.4050, 73.0810),
    ("Faisalabad", "Lyallpur Town"):                 (31.4598, 73.1022),
}

# City-centre fallback when neighbourhood is unknown
CITY_CENTRES: dict[str, tuple[float, float]] = {
    "Lahore":     (31.5204, 74.3587),
    "Karachi":    (24.8607, 67.0011),
    "Islamabad":  (33.6844, 73.0479),
    "Rawalpindi": (33.5651, 73.0169),
    "Faisalabad": (31.4504, 73.1350),
    "Multan":     (30.1575, 71.5249),
    "Peshawar":   (34.0150, 71.5249),
    "Gujranwala": (32.1877, 74.1945),
    "Quetta":     (30.1798, 66.9750),
}


def _in_bounds(lat: float, lng: float, city: str) -> bool:
    bounds = CITY_BOUNDS.get(city)
    if not bounds:
        # Unknown city — accept anything inside Pakistan's outer box
        return 23.5 <= lat <= 37.2 and 60.5 <= lng <= 77.8
    lat_min, lat_max, lng_min, lng_max = bounds
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _correct_coords(city: str, location: str) -> tuple[float, float]:
    coords = NEIGHBOURHOOD_COORDS.get((city, location))
    if coords:
        return coords
    # Partial match: key "City Housing" matches document location "City Housing, Samundari Road"
    loc_lower = location.lower()
    for (c, loc), coord in NEIGHBOURHOOD_COORDS.items():
        if c == city and (loc.lower() in loc_lower or loc_lower in loc.lower()):
            return coord
    return CITY_CENTRES.get(city, (31.5204, 74.3587))


async def run(apply: bool) -> None:
    uri = settings.mongodb_uri
    kwargs: dict = {}
    if "mongodb+srv://" in uri.lower() or "tls=true" in uri.lower():
        kwargs["tlsCAFile"] = certifi.where()

    client = AsyncIOMotorClient(uri, **kwargs)
    db = client[settings.mongodb_db_name]
    col = db["properties"]

    total = await col.count_documents({})
    print(f"Scanning {total} properties  (apply={apply})\n")

    fixed = 0
    skipped = 0

    async for doc in col.find({}, {"_id": 1, "title": 1, "city": 1, "location": 1,
                                   "latitude": 1, "longitude": 1}):
        lat = doc.get("latitude")
        lng = doc.get("longitude")
        city = doc.get("city", "")
        location = doc.get("location", "")

        if lat is None or lng is None:
            skipped += 1
            continue

        if _in_bounds(lat, lng, city):
            continue

        new_lat, new_lng = _correct_coords(city, location)
        title = (doc.get("title") or "")[:55]
        print(
            f"  BAD  [{city:12s}] {title:55s}  "
            f"was ({lat:.4f}, {lng:.4f})  ->  ({new_lat:.4f}, {new_lng:.4f})"
        )

        if apply:
            await col.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "latitude":  new_lat,
                        "longitude": new_lng,
                        "geo_point": {
                            "type": "Point",
                            "coordinates": [new_lng, new_lat],
                        },
                    }
                },
            )
        fixed += 1

    client.close()
    action = "Fixed" if apply else "Would fix"
    print(f"\n{action} {fixed} properties  |  skipped (no coords): {skipped}")
    if not apply and fixed:
        print("Run with --apply to write these corrections to MongoDB.")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Fix property coordinates that are outside their city bounds.")
    ap.add_argument("--apply", action="store_true", help="Write fixes to MongoDB (default: dry-run)")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(apply=args.apply))
