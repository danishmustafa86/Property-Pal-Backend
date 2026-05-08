import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import current_user
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse, QueryHistoryRecord
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()
service = ChatService()


@router.post("/query", response_model=ChatQueryResponse)
async def chat_query(payload: ChatQueryRequest, user: dict = Depends(current_user)):
    try:
        return await service.query(user, payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Chat query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI agent error: {exc.__class__.__name__}: {exc}",
        ) from exc


@router.get("/history", response_model=list[QueryHistoryRecord])
async def chat_history(user: dict = Depends(current_user)):
    return await service.history(user)
