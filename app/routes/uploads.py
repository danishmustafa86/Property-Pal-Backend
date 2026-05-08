from fastapi import APIRouter, Depends, File, UploadFile

from app.auth.dependencies import current_user
from app.services.upload_service import UploadService

router = APIRouter()
service = UploadService()


@router.post("/images")
async def upload_image(file: UploadFile = File(...), _: dict = Depends(current_user)):
    url = await service.upload_image(file)
    return {"url": url}
