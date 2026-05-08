import asyncio
import statistics
import time

import httpx


async def hit(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> float:
    start = time.perf_counter()
    await client.get(url, headers=headers)
    return (time.perf_counter() - start) * 1000


async def main():
    base_url = "http://127.0.0.1:8000"
    headers = {"Authorization": "Bearer <CLERK_TOKEN>"}
    endpoints = ["/search/", "/map-properties/?min_lat=31&min_lng=74&max_lat=32&max_lng=75", "/chat/history"]

    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        for ep in endpoints:
            latencies = []
            for _ in range(20):
                latencies.append(await hit(client, ep, headers))
            p95 = statistics.quantiles(latencies, n=20)[-1]
            print(f"{ep} -> avg={statistics.mean(latencies):.2f}ms p95={p95:.2f}ms")


if __name__ == "__main__":
    asyncio.run(main())
