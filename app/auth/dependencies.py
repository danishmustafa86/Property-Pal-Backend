from fastapi import Depends, Header, HTTPException, status
import hashlib

from app.auth.clerk import parse_bearer_token, verify_clerk_token
from app.repositories.users import UserRepository
from app.schemas.common import serialize_mongo_id


async def current_user(authorization: str | None = Header(default=None)) -> dict:
    token = parse_bearer_token(authorization)
    payload = verify_clerk_token(token)
    clerk_user_id = payload.get("sub")
    email = payload.get("email") or payload.get("email_address")
    if not email and isinstance(payload.get("email_addresses"), list) and payload["email_addresses"]:
        first = payload["email_addresses"][0]
        if isinstance(first, dict):
            email = first.get("email_address")
    full_name = payload.get("name") or payload.get("username") or "Unknown User"
    if clerk_user_id and not email:
        existing_user = await UserRepository().get_by_clerk_id(clerk_user_id)
        if existing_user and existing_user.get("email"):
            email = existing_user.get("email")
        else:
            # Clerk session tokens may omit email claims; create a stable synthetic email key for local profile storage.
            stable_local = hashlib.sha256(clerk_user_id.encode("utf-8")).hexdigest()[:24]
            email = f"{stable_local}@clerk.local"
    if not clerk_user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Clerk claims.")

    user = await UserRepository().upsert_clerk_user(clerk_user_id=clerk_user_id, email=email, full_name=full_name)
    return serialize_mongo_id(user)


async def current_user_optional(authorization: str | None = Header(default=None)) -> dict | None:
    if not authorization:
        return None
    try:
        return await current_user(authorization)
    except HTTPException:
        return None


def require_role(*roles: str):
    async def role_dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role permissions.")
        return user

    return role_dependency
