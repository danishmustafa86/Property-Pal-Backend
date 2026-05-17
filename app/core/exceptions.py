from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(ServerSelectionTimeoutError)
    @app.exception_handler(ConfigurationError)
    async def mongo_error_handler(_: Request, exc: Exception):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": (
                        "Cannot reach MongoDB. On university/campus Wi‑Fi, mongodb+srv:// DNS often "
                        "times out — use Atlas 'Standard connection string' in MONGODB_URI, or "
                        "mongodb://localhost:27017 for local dev."
                    ),
                    "detail": str(exc),
                }
            },
        )
