import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from redis.exceptions import RedisError

from database import get_db
from models import User
from services.auth import AuthService
from services.chat import ChatService
from schemas import (
    ChatJobAccepted,
    ChatJobStatus,
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
)


router = APIRouter(prefix="/chat", tags=["chat"])
auth_service = AuthService()
chat_service = ChatService()
logger = logging.getLogger(__name__)

@router.post("/message", response_model=ChatJobAccepted, status_code=202)
def send_message_route(
    payload: ChatRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.enqueue_message(payload, user, db, idempotency_key)


@router.get("/jobs/{job_id}", response_model=ChatJobStatus)
def get_chat_job_route(
    job_id: int,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.get_job_status(job_id, user, db)


@router.get("/jobs/{job_id}/events")
async def stream_chat_job_route(
    job_id: int,
    request: Request,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    job = chat_service.get_job_status(job_id, user, db)
    db.close()  # Don't hold a PostgreSQL connection for the lifetime of SSE.
    redis_client = getattr(request.app.state, "redis_events", None)
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Live updates are temporarily unavailable. Poll the job status instead.")

    async def event_stream():
        stream_key = f"minix:chat:job-events:{job_id}"
        cursor = "0-0"
        if job.status in {"completed", "failed"}:
            yield f"event: {job.status}\ndata: {job.model_dump_json()}\n\n"
            return
        while True:
            if await request.is_disconnected():
                return
            try:
                batches = await redis_client.xread({stream_key: cursor}, count=100, block=10000)
            except RedisError:
                logger.warning("Redis job event stream disconnected", exc_info=True)
                yield "event: unavailable\ndata: {}\n\n"
                return
            if not batches:
                yield ": keep-alive\n\n"
                continue
            for _, events in batches:
                for event_id, fields in events:
                    cursor = event_id
                    event_type = fields.get("type", "message")
                    data = fields.get("data", "{}")
                    yield f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"
                    if event_type in {"completed", "failed"}:
                        return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[ConversationOut])
def list_conversations_route(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.list_conversations(user, db)


@router.get("/history/{conversation_id}", response_model=ConversationDetail)
def get_conversation_route(
    conversation_id: int,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.get_conversation(conversation_id, user, db)


@router.post("/history", response_model=ConversationDetail)
def create_conversation_route(
    payload: ConversationCreate,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.create_conversation(payload, user, db)


@router.delete("/history/{conversation_id}")
def delete_conversation_route(
    conversation_id: int,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.delete_conversation(conversation_id, user, db)


@router.delete("/history")
def clear_history_route(
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    return chat_service.clear_history(user, db)
