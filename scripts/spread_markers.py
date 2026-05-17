"""
Spread properties that share the exact same coordinates using a golden-angle
spiral so every marker is individually visible on the map.

Each group of stacked properties is laid out in a Fibonacci spiral:
  - property 0 keeps the original geocoded position
  - properties 1-N are placed at ~60 m spacing in a golden-angle spiral

Usage:
    cd backend
    PYTHONPATH=. python scripts/spread_markers.py           # dry-run
    PYTHONPATH=. python scripts/spread_markers.py --apply   # write to DB
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

# Golden angle in radians — produces the most uniform spiral distribution
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))

# Spacing between rings in metres.  60 m keeps pins clearly separate at city
# zoom levels without moving them far from the true neighbourhood centre.
_SPREAD_M = 60.0

# Resolution for grouping: 4 d.p. ≈ 11 m — treat positions closer than this
# as identical and eligible for spreading.
_ROUND = 4


def _spiral_offset(index: int, lat_centre: float) -> tuple[float, float]:
    """Return (delta_lat, delta_lng) in degrees for the index-th spiral point."""
    if index == 0:
        return 0.0, 0.0
    r = _SPREAD_M * math.sqrt(index)
    theta = index * _GOLDEN_ANGLE
    d_lat = r * math.cos(theta) / 111_320.0
    d_lng = r * math.sin(theta) / (111_320.0 * math.cos(math.radians(lat_centre)))
    return d_lat, d_lng


async def run(apply: bool) -> None:
    uri = settings.mongodb_uri
    kwargs: dict = {}
    if "mongodb+srv://" in uri.lower() or "tls=true" in uri.lower():
        kwargs["tlsCAFile"] = certifi.where()

    mongo = AsyncIOMotorClient(uri, **kwargs)
    col = mongo[settings.mongodb_db_name]["properties"]

    docs = await col.find(
        {"listing_status": "active", "latitude": {"$exists": True}},
        {"_id": 1, "title": 1, "city": 1, "latitude": 1, "longitude": 1},
    ).to_list(length=None)

    # Group by rounded coordinate
    groups: dict[tuple[float, float], list[dict]] = {}
    for doc in docs:
        key = (round(doc["latitude"], _ROUND), round(doc["longitude"], _ROUND))
        groups.setdefault(key, []).append(doc)

    stacked = {k: v for k, v in groups.items() if len(v) > 1}
    total_affected = sum(len(v) for v in stacked.values())

    print(f"Total active properties : {len(docs)}")
    print(f"Unique positions         : {len(groups)}")
    print(f"Stacked positions        : {len(stacked)}")
    print(f"Properties needing spread: {total_affected}")
    print(f"Mode                     : {'APPLY' if apply else 'DRY-RUN'}")
    print()

    moved = 0
    for (lat0, lng0), group in stacked.items():
        for i, doc in enumerate(group):
            if i == 0:
                continue  # first one keeps original position
            d_lat, d_lng = _spiral_offset(i, lat0)
            new_lat = round(lat0 + d_lat, 6)
            new_lng = round(lng0 + d_lng, 6)
            title = (doc.get("title") or "")[:50]
            print(
                f"  [{doc.get('city',''):12s}] {title:50s}  "
                f"({lat0:.5f},{lng0:.5f}) -> ({new_lat:.5f},{new_lng:.5f})"
            )
            if apply:
                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "latitude":  new_lat,
                        "longitude": new_lng,
                        "geo_point": {"type": "Point", "coordinates": [new_lng, new_lat]},
                    }},
                )
            moved += 1

    mongo.close()
    print()
    action = "Moved" if apply else "Would move"
    print(f"{action} {moved} properties into spiral positions.")
    if not apply:
        print("Run with --apply to write to MongoDB.")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Spread stacked map markers using a golden-angle spiral.")
    ap.add_argument("--apply", action="store_true", help="Write to MongoDB (default: dry-run)")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(apply=args.apply))
