from bson import ObjectId

from app.models.collections import USERS_COLLECTION
from app.repositories.base import BaseRepository

_SYNTHETIC_EMAIL_SUFFIX = "@clerk.local"
_DEFAULT_NAME = "Unknown User"


class UserRepository(BaseRepository):
    collection_name = USERS_COLLECTION

    async def get_by_id(self, user_id: str):
        return await self.collection.find_one({"_id": ObjectId(user_id)})

    async def get_by_clerk_id(self, clerk_user_id: str):
        return await self.collection.find_one({"clerk_user_id": clerk_user_id})

    async def upsert_clerk_user(self, clerk_user_id: str, email: str, full_name: str):
        doc = await self.collection.find_one({"clerk_user_id": clerk_user_id})
        if doc:
            update: dict = {"updated_at": self.now()}
            existing_email = doc.get("email", "")
            existing_name = doc.get("full_name", "")

            is_new_email_real = email and not email.endswith(_SYNTHETIC_EMAIL_SUFFIX)
            is_existing_email_real = existing_email and not existing_email.endswith(_SYNTHETIC_EMAIL_SUFFIX)
            if is_new_email_real or not is_existing_email_real:
                update["email"] = email

            is_new_name_real = full_name and full_name != _DEFAULT_NAME
            is_existing_name_real = existing_name and existing_name != _DEFAULT_NAME
            if is_new_name_real or not is_existing_name_real:
                update["full_name"] = full_name

            await self.collection.update_one({"_id": doc["_id"]}, {"$set": update})
            doc.update(update)
            return doc

        payload = {
            "clerk_user_id": clerk_user_id,
            "email": email,
            "full_name": full_name,
            "role": "user",
            "phone_verified": False,
            "created_at": self.now(),
            "updated_at": self.now(),
        }
        result = await self.collection.insert_one(payload)
        payload["_id"] = result.inserted_id
        return payload

    async def update_profile(self, user_id: str, payload: dict):
        return await self.update_one_return_doc(ObjectId(user_id), payload)
