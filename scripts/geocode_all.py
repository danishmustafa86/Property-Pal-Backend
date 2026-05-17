"""
Geocode every property in MongoDB using the Google Geocoding API,
then update latitude, longitude, and geo_point with exact coordinates.

Usage:
    cd backend
    PYTHONPATH=. python scripts/geocode_all.py              # dry-run
    PYTHONPATH=. python scripts/geocode_all.py --apply      # write to DB
    PYTHONPATH=. python scripts/geocode_all.py --apply --force   # re-geocode already-done ones
    PYTHONPATH=. python scripts/geocode_all.py --apply --city Faisalabad
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import certifi
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
API_KEY = settings.google_maps_api_key

# In-process cache: query string -> (lat, lng) so identical addresses
# don't burn extra API calls.
_cache: dict[str, tuple[float, float] | None] = {}


def _build_query(doc: dict) -> str:
    """
    Build the most specific geocoding query possible from the property document.
    Priority: society + location + sub_area > location > city centre.
    All queries are anchored to Pakistan.
    """
    parts: list[str] = []

    society  = (doc.get("society")  or "").strip()
    location = (doc.get("location") or "").strip()
    sub_area = (doc.get("sub_area") or "").strip()
    city     = (doc.get("city")     or "").strip()
    province = (doc.get("province") or "").strip()

    # Add society only if it adds information beyond what's already in location
    if society and society.lower() not in location.lower():
        parts.append(society)

    if location:
        parts.append(location)

    # sub_area sometimes has a block/phase that helps pinpoint the pin
    if sub_area and sub_area.lower() not in " ".join(parts).lower():
        parts.append(sub_area)

    if city:
        parts.append(city)
    if province:
        parts.append(province)

    parts.append("Pakistan")
    return ", ".join(parts)


async def _geocode(client: httpx.AsyncClient, query: str) -> tuple[float, float] | None:
    if query in _cache:
        return _cache[query]

    params = {
        "address":    query,
        "key":        API_KEY,
        "region":     "pk",
        "components": "country:PK",
    }
    try:
        resp = await client.get(GEOCODE_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"    [HTTP error] {exc}")
        _cache[query] = None
        return None

    if data.get("status") != "OK" or not data.get("results"):
        _cache[query] = None
        return None

    loc = data["results"][0]["geometry"]["location"]
    result = (float(loc["lat"]), float(loc["lng"]))
    _cache[query] = result
    return result


def _fmt(seconds: float) -> str:
    return f"{seconds:.0f}s" if seconds < 60 else f"{seconds/60:.1f}min"


async def run(*, apply: bool, force: bool, city_filter: str | None, concurrency: int) -> None:
    if not API_KEY:
        print("ERROR: GOOGLE_MAPS_API_KEY is not set in .env")
        sys.exit(1)

    client_kwargs: dict = {}
    uri = settings.mongodb_uri
    if "mongodb+srv://" in uri.lower() or "tls=true" in uri.lower():
        client_kwargs["tlsCAFile"] = certifi.where()

    mongo = AsyncIOMotorClient(uri, **client_kwargs)
    db    = mongo[settings.mongodb_db_name]
    col   = db["properties"]

    mongo_filter: dict = {}
    if city_filter:
        mongo_filter["city"] = {"$regex": city_filter, "$options": "i"}
    if not force:
        # Skip properties already geocoded by this script (flagged by geocoded_at)
        mongo_filter["geocoded_at"] = {"$exists": False}

    total = await col.count_documents(mongo_filter)
    print(f"\nGoogle Geocoding - exact coordinates for every property")
    print(f"  API key : ...{API_KEY[-8:]}")
    print(f"  Mode    : {'APPLY (writes to DB)' if apply else 'DRY-RUN (no writes)'}")
    print(f"  Force   : {force}")
    print(f"  City    : {city_filter or 'all'}")
    print(f"  Target  : {total} properties")
    print(f"  Workers : {concurrency}")
    print()

    if total == 0:
        if force:
            print("No properties found.")
        else:
            print("All properties already geocoded. Use --force to re-geocode.")
        mongo.close()
        return

    docs = await col.find(
        mongo_filter,
        {"_id": 1, "title": 1, "city": 1, "location": 1, "society": 1,
         "sub_area": 1, "province": 1, "latitude": 1, "longitude": 1}
    ).to_list(length=None)

    sem      = asyncio.Semaphore(concurrency)
    counters = {"ok": 0, "failed": 0, "cached": 0}
    start_ts = time.time()

    async with httpx.AsyncClient() as http:

        async def process(doc: dict) -> None:
            async with sem:
                prop_id  = doc["_id"]
                title    = (doc.get("title") or "")[:50]
                city     = doc.get("city", "")
                query    = _build_query(doc)
                old_lat  = doc.get("latitude", 0)
                old_lng  = doc.get("longitude", 0)

                was_cached = query in _cache
                coords = await _geocode(http, query)

                done = counters["ok"] + counters["failed"] + 1
                pct  = done / total * 100
                elapsed = time.time() - start_ts
                eta = (elapsed / done * (total - done)) if done > 0 else 0

                if coords is None:
                    counters["failed"] += 1
                    status = "FAILED"
                    print(f"  [{done:3d}/{total}] {pct:3.0f}%  [{city:12s}]  {title:50s}  {status}")
                    print(f"           query: {query}")
                    return

                new_lat, new_lng = coords
                if was_cached:
                    counters["cached"] += 1

                moved = abs(new_lat - old_lat) > 0.001 or abs(new_lng - old_lng) > 0.001
                tag   = "MOVED " if moved else "same  "

                print(
                    f"  [{done:3d}/{total}] {pct:3.0f}%  [{city:12s}]  {title:50s}  "
                    f"{tag}  ({new_lat:.5f}, {new_lng:.5f})  eta={_fmt(eta)}"
                )

                if apply:
                    from datetime import datetime, timezone
                    await col.update_one(
                        {"_id": prop_id},
                        {"$set": {
                            "latitude":    new_lat,
                            "longitude":   new_lng,
                            "geo_point":   {"type": "Point", "coordinates": [new_lng, new_lat]},
                            "geocoded_at": datetime.now(timezone.utc),
                            "geocode_query": query,
                        }},
                    )

                counters["ok"] += 1
                # Small delay to stay well under Google's rate limits
                await asyncio.sleep(0.05)

        await asyncio.gather(*[process(d) for d in docs])

    mongo.close()
    elapsed = time.time() - start_ts
    print()
    print("=" * 70)
    print(f"Done in {_fmt(elapsed)}")
    print(f"  Geocoded OK : {counters['ok']}  (cache hits: {counters['cached']})")
    print(f"  Failed      : {counters['failed']}")
    if not apply:
        print()
        print("Run with --apply to write these coordinates to MongoDB.")
    print("=" * 70)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Geocode all properties with Google API.")
    ap.add_argument("--apply",       action="store_true", help="Write results to MongoDB")
    ap.add_argument("--force",       action="store_true", help="Re-geocode already-done properties")
    ap.add_argument("--city",        default=None,        help="Filter to one city")
    ap.add_argument("--concurrency", type=int, default=5, help="Parallel workers (default 5)")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(
        apply=args.apply,
        force=args.force,
        city_filter=args.city,
        concurrency=min(args.concurrency, 10),
    ))
