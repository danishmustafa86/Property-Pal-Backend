"""
Bulk enrich all existing properties with real Google Places data.

Usage:
    python scripts/enrich_places.py                   # enrich only un-enriched properties
    python scripts/enrich_places.py --force           # re-enrich ALL properties
    python scripts/enrich_places.py --limit 50        # process at most 50 properties
    python scripts/enrich_places.py --city Lahore     # only properties in a specific city
    python scripts/enrich_places.py --dry-run         # show what would be processed, no API calls
    python scripts/enrich_places.py --radius 2.5      # search radius in km (default 2.0)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

# Make the backend package importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.places_service import PlacesService


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}min"


def _progress(done: int, total: int, start_ts: float) -> str:
    pct = done / total * 100 if total else 0
    elapsed = time.time() - start_ts
    eta = (elapsed / done * (total - done)) if done > 0 else 0
    return f"[{done}/{total}] {pct:.0f}%  elapsed={_fmt_time(elapsed)}  eta={_fmt_time(eta)}"


# ── Main enrichment logic ──────────────────────────────────────────────────────

async def run(
    *,
    force: bool,
    limit: int | None,
    city: str | None,
    dry_run: bool,
    radius_km: float,
    concurrency: int,
) -> None:
    svc = PlacesService()
    if not svc.is_configured():
        print("ERROR: GOOGLE_MAPS_API_KEY is not set in .env — aborting.")
        sys.exit(1)

    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.mongodb_uri, tlsCAFile=certifi.where())
    db = client[settings.mongodb_db_name]
    col = db["properties"]

    # Build query — only properties that have coordinates
    mongo_filter: dict = {
        "latitude": {"$exists": True, "$ne": None},
        "longitude": {"$exists": True, "$ne": None},
    }
    if not force:
        # Skip properties already enriched (nearby_places non-empty)
        mongo_filter["$or"] = [
            {"nearby_places": {"$exists": False}},
            {"nearby_places": {"$size": 0}},
        ]
    if city:
        mongo_filter["city"] = {"$regex": city, "$options": "i"}

    total = await col.count_documents(mongo_filter)
    if limit:
        total = min(total, limit)

    print(f"\nGoogle Places bulk enrichment")
    print(f"  Mode    : {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  Force   : {force}")
    print(f"  City    : {city or 'all'}")
    print(f"  Radius  : {radius_km} km")
    print(f"  Target  : {total} properties")
    print(f"  Workers : {concurrency}")
    print()

    if total == 0:
        print("Nothing to enrich. All properties already have Places data.")
        print("Run with --force to re-enrich everything.")
        client.close()
        return

    if dry_run:
        cursor = col.find(mongo_filter, {"_id": 1, "title": 1, "city": 1, "latitude": 1, "longitude": 1})
        if limit:
            cursor = cursor.limit(limit)
        async for doc in cursor:
            print(f"  would enrich: {doc.get('title', '?')[:50]} | {doc.get('city')} | lat={doc.get('latitude'):.4f} lng={doc.get('longitude'):.4f}")
        client.close()
        return

    # ── Semaphore-limited concurrent enrichment ─────────────────────────────
    sem = asyncio.Semaphore(concurrency)
    counters = {"done": 0, "ok": 0, "skipped": 0, "error": 0}
    start_ts = time.time()

    cursor = col.find(mongo_filter, {"_id": 1, "title": 1, "city": 1, "latitude": 1, "longitude": 1})
    if limit:
        cursor = cursor.limit(limit)
    docs = await cursor.to_list(length=limit or 50_000)

    async def enrich_one(doc: dict) -> None:
        async with sem:
            prop_id = str(doc["_id"])
            lat = doc.get("latitude")
            lng = doc.get("longitude")
            title = (doc.get("title") or "")[:45]
            city_name = doc.get("city", "")

            try:
                enriched = await svc.enrich_property_places(lat, lng, radius_m=radius_km * 1000)
                n_places = len(enriched.get("nearby_places", []))

                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {**enriched, "places_enriched_at": datetime.now(timezone.utc)}},
                )
                counters["ok"] += 1
                status = f"OK ({n_places} places)"
            except Exception as exc:
                counters["error"] += 1
                status = f"ERROR: {exc}"

            counters["done"] += 1
            prog = _progress(counters["done"], len(docs), start_ts)
            print(f"  {prog}  |  {city_name:12s}  {title:45s}  {status}")

            # Polite delay to stay under Google rate limits
            # 7 calls/property × concurrency workers × delay ≈ safe throughput
            await asyncio.sleep(0.3)

    await asyncio.gather(*[enrich_one(doc) for doc in docs])

    elapsed = time.time() - start_ts
    print()
    print("=" * 70)
    print(f"Enrichment complete in {_fmt_time(elapsed)}")
    print(f"  Enriched OK : {counters['ok']}")
    print(f"  Errors      : {counters['error']}")
    print(f"  Total       : {counters['done']}")
    print("=" * 70)
    client.close()


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Bulk enrich properties with Google Places data.")
    ap.add_argument("--force",       action="store_true", help="Re-enrich even already-enriched properties")
    ap.add_argument("--limit",       type=int,   default=None, help="Max properties to process")
    ap.add_argument("--city",        type=str,   default=None, help="Filter by city name")
    ap.add_argument("--dry-run",     action="store_true", help="List properties that would be enriched, no API calls")
    ap.add_argument("--radius",      type=float, default=2.0,  help="Search radius in km (default 2.0)")
    ap.add_argument("--concurrency", type=int,   default=3,    help="Parallel workers (default 3, max 5)")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run(
            force=args.force,
            limit=args.limit,
            city=args.city,
            dry_run=args.dry_run,
            radius_km=args.radius,
            concurrency=min(args.concurrency, 5),
        )
    )
