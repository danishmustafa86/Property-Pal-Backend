from functools import lru_cache

import httpx
import jwt
from fastapi import HTTPException, status

from app.core.config import settings


def resolved_clerk_jwks_url() -> str:
    if settings.clerk_jwks_url:
        return str(settings.clerk_jwks_url)
    issuer = (settings.clerk_issuer or "").strip().rstrip("/")
    if issuer:
        return f"{issuer}/.well-known/jwks.json"
    raise RuntimeError(
        "Clerk JWT verification is not configured. Set CLERK_ISSUER (Frontend API URL) "
        "or CLERK_JWKS_URL in the backend .env — see backend/.env.example."
    )


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def _get_jwks_client() -> jwt.PyJWKClient:
    return _jwks_client(resolved_clerk_jwks_url())


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header.")
    parts = authorization.split(" ", maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header.")
    return parts[1]


def verify_clerk_token(token: str) -> dict:
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        audience = settings.clerk_audience if settings.clerk_audience else None
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=settings.clerk_issuer if settings.clerk_issuer else None,
            options={"verify_aud": bool(audience), "verify_iss": bool(settings.clerk_issuer)},
        )
        return payload
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Clerk token.") from exc


async def fetch_clerk_user(clerk_user_id: str, secret_key: str | None = None) -> dict:
    key = (secret_key or settings.clerk_secret_key or "").strip()
    if not key:
        raise ValueError("CLERK_SECRET_KEY is not configured.")
    url = f"https://api.clerk.com/v1/users/{clerk_user_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    return response.json()
