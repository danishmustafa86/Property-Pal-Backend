import cloudinary
import cloudinary.uploader
from fastapi import UploadFile

from app.core.config import settings


class UploadService:
    def __init__(self) -> None:
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )

    async def upload_image(self, file: UploadFile) -> str:
        content = await file.read()
        result = cloudinary.uploader.upload(content, resource_type="image", folder="real-estate")
        return result["secure_url"]
