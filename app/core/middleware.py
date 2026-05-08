from collections import defaultdict, deque
from time import time

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        now = time()
        queue = self.events[key]
        while queue and now - queue[0] > self.window_seconds:
            queue.popleft()
        if len(queue) >= self.max_requests:
            return False
        queue.append(now)
        return True


limiter = InMemoryRateLimiter(max_requests=100, window_seconds=60)


def register_middlewares(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        path = request.url.path
        guarded_prefixes = ("/search", "/chat", "/uploads")
        if path.startswith(guarded_prefixes):
            key = request.client.host if request.client else "unknown"
            if not limiter.hit(f"{key}:{path}"):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again shortly."},
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", "generated-request-id")
        return response
