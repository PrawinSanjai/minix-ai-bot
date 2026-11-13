"""Database operations for chat conversations and background replies."""

import hashlib
import json
from contextlib import ExitStack
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import Configuration
from models import ChatJob, Conversation, Message, User
from schemas import (
    ChatJobAccepted,
    ChatJobStatus,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ChatRequest,
)
from services import cache

config = Configuration()

WELCOME_MESSAGES = {
    "stress": "I hear you. Life can feel overwhelming sometimes. Take a deep breath — I'm here with you. What's weighing on your heart?",
    "anxiety": "I understand that anxious feeling. You're safe here. Let's work through this together. What's been worrying you?",
    "career": "Your career journey matters, and it's natural to have mixed feelings about it. What's on your mind regarding work or your professional path?",
    "relationships": "Relationships shape so much of our lives. Whether it's joy or struggle you're experiencing, I'm here to listen. What would you like to share?",
    "general": "I'm glad you're here. This is your space to express whatever comes to mind. How are you feeling right now?",
}


class ChatService:
    def _welcome_message(self, topic: str | None) -> str:
        topic = (topic or "").lower()
        for keyword, message in WELCOME_MESSAGES.items():
            if keyword in topic:
                return message
        return WELCOME_MESSAGES["general"]

    def enqueue_message(
        self,
        payload: ChatRequest,
        user: User,
        db: Session,
        idempotency_key: str,
    ) -> ChatJobAccepted:
        request_data = {
            "message": payload.message,
            "conversation_id": payload.conversation_id,
            "topic": payload.topic,
        }
        request_hash = hashlib.sha256(
            json.dumps(request_data, sort_keys=True).encode("utf-8")
        ).hexdigest()

        existing = self._find_job(db, user.id, idempotency_key)
        if existing:
            return self._check_existing_job(existing, request_hash)

        conversation = self._get_or_create_conversation(payload, user, db)
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
        )
        db.add(user_message)
        db.flush()

        job = ChatJob(
            user_id=user.id,
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status="queued",
        )
        db.add(job)
        conversation.updated_at = datetime.now(timezone.utc)

        try:
            db.flush()
            db.commit()
        except IntegrityError:
            # Another identical request may have committed at the same time.
            db.rollback()
            existing = self._find_job(db, user.id, idempotency_key)
            if not existing:
                raise
            return self._check_existing_job(existing, request_hash)

        cache.bump_generation(user.id)
        return ChatJobAccepted(
            job_id=job.id,
            conversation_id=conversation.id,
            status=job.status,
        )

    def _find_job(self, db: Session, user_id: int, idempotency_key: str) -> ChatJob | None:
        return db.query(ChatJob).filter(
            ChatJob.user_id == user_id,
            ChatJob.idempotency_key == idempotency_key,
        ).first()

    def _check_existing_job(self, job: ChatJob, request_hash: str) -> ChatJobAccepted:
        if job.request_hash != request_hash:
            raise HTTPException(
                status_code=409,
                detail="This idempotency key was already used for a different message.",
            )
        return ChatJobAccepted(
            job_id=job.id,
            conversation_id=job.conversation_id,
            status=job.status,
        )

    def _get_or_create_conversation(
        self,
        payload: ChatRequest,
        user: User,
        db: Session,
    ) -> Conversation:
        if payload.conversation_id is not None:
            conversation = db.query(Conversation).filter(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == user.id,
            ).first()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            return conversation

        topic = (payload.topic or "general")[:100]
        conversation = Conversation(
            user_id=user.id,
            title=payload.message[:50],
            topic=topic,
        )
        db.add(conversation)
        db.flush()
        db.add(Message(
            conversation_id=conversation.id,
            role="bot",
            content=self._welcome_message(topic),
        ))
        db.flush()
        return conversation

    def get_job_status(self, job_id: int, user: User, db: Session) -> ChatJobStatus:
        job = db.query(ChatJob).filter(
            ChatJob.id == job_id,
            ChatJob.user_id == user.id,
        ).first()
        if not job:
            raise HTTPException(status_code=404, detail="Chat job not found")

        reply = None
        if job.assistant_message_id:
            reply = db.query(Message.content).filter(
                Message.id == job.assistant_message_id,
            ).scalar()

        return ChatJobStatus(
            job_id=job.id,
            conversation_id=job.conversation_id,
            status=job.status,
            reply=reply,
            error=job.error,
        )

    def list_conversations(self, user: User, db: Session) -> list[ConversationOut]:
        version = cache.generation(user.id)
        cache_key = f"minix:chat:history:{user.id}:v{version}"
        cached = cache.get_json(cache_key)
        if cached is not None:
            return [ConversationOut.model_validate(item) for item in cached]

        latest_user_message = (
            db.query(Message.content)
            .filter(
                Message.conversation_id == Conversation.id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )
        rows = (
            db.query(Conversation, latest_user_message.label("preview"))
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )

        conversations = []
        for conversation, preview in rows:
            conversations.append(ConversationOut(
                id=conversation.id,
                title=conversation.title,
                topic=conversation.topic,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                preview=preview[:50] if preview else "",
                time=conversation.updated_at.strftime("%H:%M") if conversation.updated_at else "",
            ))

        if cache.generation(user.id) == version:
            cache.set_json(
                cache_key,
                [item.model_dump(mode="json") for item in conversations],
                config.REDIS_CACHE_TTL_SECONDS,
            )
        return conversations

    def get_conversation(
        self,
        conversation_id: int,
        user: User,
        db: Session,
    ) -> Conversation | dict:
        version = cache.generation(user.id)
        cache_key = f"minix:chat:conversation:{user.id}:{conversation_id}:v{version}"
        cached = cache.get_json(cache_key)
        if cached is not None:
            return cached

        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        ).first()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if cache.generation(user.id) == version:
            detail = ConversationDetail.model_validate(conversation).model_dump(mode="json")
            cache.set_json(cache_key, detail, config.REDIS_CACHE_TTL_SECONDS)
        return conversation

    def create_conversation(
        self,
        payload: ConversationCreate,
        user: User,
        db: Session,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user.id,
            title=payload.title,
            topic=payload.topic,
        )
        db.add(conversation)
        db.flush()

        for message in payload.messages:
            db.add(Message(
                conversation_id=conversation.id,
                role=message.get("role", "user"),
                content=message.get("content", ""),
            ))

        db.commit()
        db.refresh(conversation)
        cache.bump_generation(user.id)
        return conversation

    def delete_conversation(self, conversation_id: int, user: User, db: Session) -> dict:
        with cache.conversation_lock(user.id, conversation_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=409,
                    detail="This conversation is processing a message. Try again shortly.",
                )
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            ).first()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            db.delete(conversation)
            db.commit()
            cache.bump_generation(user.id)
            return {"message": "Conversation deleted"}

    def clear_history(self, user: User, db: Session) -> dict:
        conversation_ids = [row[0] for row in db.query(Conversation.id).filter(
            Conversation.user_id == user.id,
        ).all()]

        with ExitStack() as locks:
            for conversation_id in conversation_ids:
                acquired = locks.enter_context(cache.conversation_lock(
                    user.id,
                    conversation_id,
                    blocking_timeout=0.1,
                ))
                if not acquired:
                    raise HTTPException(
                        status_code=409,
                        detail="A conversation is processing a message. Try again shortly.",
                    )

            conversations = db.query(Conversation).filter(
                Conversation.user_id == user.id,
            ).all()
            for conversation in conversations:
                db.delete(conversation)
            db.commit()
            cache.bump_generation(user.id)
            return {"message": "All conversations cleared"}
