from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
from contextlib import ExitStack
import hashlib
import json

from services.llm import LLM_Service
from services.rag import RAG_Service
from schemas import ChatRequest, ChatResponse, ChatJobAccepted, ChatJobStatus, ConversationOut, ConversationDetail, ConversationCreate
from models import User, Conversation, Message, ChatJob, JobOutbox
from services import cache
from config import Configuration

config = Configuration()

llm_service = LLM_Service()
rag_service = RAG_Service()

WELCOME_MESSAGES = {
    "stress": "I hear you. Life can feel overwhelming sometimes. Take a deep breath — I'm here with you. What's weighing on your heart?",
    "anxiety": "I understand that anxious feeling. You're safe here. Let's work through this together. What's been worrying you?",
    "career": "Your career journey matters, and it's natural to have mixed feelings about it. What's on your mind regarding work or your professional path?",
    "relationships": "Relationships shape so much of our lives. Whether it's joy or struggle you're experiencing, I'm here to listen. What would you like to share?",
    "general": "I'm glad you're here. This is your space to express whatever comes to mind. How are you feeling right now?",
}


class Chat_Service():
    def _get_welcome(self, topic: str | None) -> str:
        lower = (topic or "").lower()
        for key, msg in WELCOME_MESSAGES.items():
            if key in lower:
                return msg
        return WELCOME_MESSAGES["general"]


    def enqueue_message(self, payload: ChatRequest, user: User, db: Session, idempotency_key: str) -> ChatJobAccepted:
        request_hash = hashlib.sha256(json.dumps({
            "message": payload.message,
            "conversation_id": payload.conversation_id,
            "topic": payload.topic,
        }, sort_keys=True).encode("utf-8")).hexdigest()
        existing = db.query(ChatJob).filter(
            ChatJob.user_id == user.id,
            ChatJob.idempotency_key == idempotency_key,
        ).first()
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(status_code=409, detail="This idempotency key was already used for a different message.")
            return ChatJobAccepted(job_id=existing.id, conversation_id=existing.conversation_id, status=existing.status)

        conversation = None
        if payload.conversation_id is not None:
            conversation = db.query(Conversation).filter(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == user.id,
            ).first()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            topic = (payload.topic or "general")[:100]
            conversation = Conversation(user_id=user.id, title=payload.message[:50], topic=topic)
            db.add(conversation)
            db.flush()
            db.add(Message(conversation_id=conversation.id, role="bot", content=self._get_welcome(topic)))
            db.flush()

        user_message = Message(conversation_id=conversation.id, role="user", content=payload.message)
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
        db.flush()
        db.add(JobOutbox(job_id=job.id))
        conversation.updated_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent retries can race past the initial idempotency lookup.
            db.rollback()
            existing = db.query(ChatJob).filter(
                ChatJob.user_id == user.id,
                ChatJob.idempotency_key == idempotency_key,
            ).first()
            if not existing:
                raise
            if existing.request_hash != request_hash:
                raise HTTPException(status_code=409, detail="This idempotency key was already used for a different message.")
            return ChatJobAccepted(job_id=existing.id, conversation_id=existing.conversation_id, status=existing.status)
        cache.bump_generation(user.id)
        return ChatJobAccepted(job_id=job.id, conversation_id=conversation.id, status=job.status)


    def get_job_status(self, job_id: int, user: User, db: Session) -> ChatJobStatus:
        job = db.query(ChatJob).filter(ChatJob.id == job_id, ChatJob.user_id == user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Chat job not found")
        reply = None
        if job.assistant_message_id:
            reply = db.query(Message.content).filter(Message.id == job.assistant_message_id).scalar()
        return ChatJobStatus(
            job_id=job.id,
            conversation_id=job.conversation_id,
            status=job.status,
            reply=reply,
            error=job.error,
        )


    def send_message(self, payload: ChatRequest, user: User, db: Session) -> ChatResponse:
        if payload.conversation_id is None:
            return self._process_message(payload, user, db)

        with cache.conversation_lock(user.id, payload.conversation_id) as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=409,
                    detail="A reply is already being generated for this conversation. Please wait and try again.",
                )
            return self._process_message(payload, user, db)


    def _process_message(self, payload: ChatRequest, user: User, db: Session) -> ChatResponse:
        conversation = None
        if payload.conversation_id is not None:
            conversation = (
                db.query(Conversation)
                .filter(Conversation.id == payload.conversation_id, Conversation.user_id == user.id)
                .first()
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

        is_new_conversation = False
        if not conversation:
            topic = payload.topic or "general"
            conversation = Conversation(
                user_id=user.id,
                title=payload.message[:50],
                topic=topic,
            )
            db.add(conversation)
            db.flush()
            is_new_conversation = True

            welcome = self._get_welcome(topic)
            db.add(Message(conversation_id=conversation.id, role="bot", content=welcome))
            db.flush()

        rag_context = rag_service.search_relevant_context(db, payload.message, user.id, limit=5)

        user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
        db.add(user_msg)
        db.flush()

        embedding = rag_service.generate_embedding(payload.message)
        if embedding:
            rag_service.store_embedding(db, user_msg.id, user.id, embedding)
            db.flush()

        all_messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        conversation_history = rag_service.build_conversation_history(all_messages, max_turns=30)

        # Persist the inbound message and release the PostgreSQL connection
        # while waiting on the model provider. Sessions check out a new pooled
        # connection only when the response needs to be saved.
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        cache.bump_generation(user.id)

        reply, emotion = llm_service.generate_chat_response(
            user_message=payload.message,
            tone=user.tone,
            conversation_history=conversation_history,
            rag_context=rag_context,
        )

        bot_msg = Message(conversation_id=conversation.id, role="bot", content=reply)
        db.add(bot_msg)
        db.flush()

        bot_embedding = rag_service.generate_embedding(reply)
        if bot_embedding:
            rag_service.store_embedding(db, bot_msg.id, user.id, bot_embedding)

        if is_new_conversation or len(all_messages) <= 2:
            conversation.title = payload.message[:50]

        db.commit()
        db.refresh(conversation)
        cache.bump_generation(user.id)

        return ChatResponse(reply=reply, conversation_id=conversation.id, emotion=emotion)


    def list_conversations(self, user: User, db: Session) -> list[ConversationOut]:
        version = cache.generation(user.id)
        cache_key = f"minix:chat:history:{user.id}:v{version}"
        cached = cache.get_json(cache_key)
        if cached is not None:
            return [ConversationOut.model_validate(item) for item in cached]

        last_user_message = (
            db.query(Message.content)
            .filter(Message.conversation_id == Conversation.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )
        conversations = (
            db.query(Conversation, last_user_message.label("preview"))
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )

        result = []
        for c, preview in conversations:
            time_str = c.updated_at.strftime("%H:%M") if c.updated_at else ""
            result.append(
                ConversationOut(
                    id=c.id,
                    title=c.title,
                    topic=c.topic,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                    preview=preview[:50] if preview else "",
                    time=time_str,
                )
            )
        if cache.generation(user.id) == version:
            cache.set_json(cache_key, [item.model_dump(mode="json") for item in result], config.REDIS_CACHE_TTL_SECONDS)
        return result


    def get_conversation(self, conversation_id: int, user: User, db: Session) -> Conversation | dict:
        version = cache.generation(user.id)
        cache_key = f"minix:chat:conversation:{user.id}:{conversation_id}:v{version}"
        cached = cache.get_json(cache_key)
        if cached is not None:
            return cached

        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if cache.generation(user.id) == version:
            detail = ConversationDetail.model_validate(conversation).model_dump(mode="json")
            cache.set_json(cache_key, detail, config.REDIS_CACHE_TTL_SECONDS)
        return conversation


    def create_conversation(self, payload: ConversationCreate, user: User, db: Session) -> Conversation:
        conversation = Conversation(
            user_id=user.id,
            title=payload.title,
            topic=payload.topic,
        )
        db.add(conversation)
        db.flush()

        for msg in payload.messages:
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                )
            )

        db.commit()
        db.refresh(conversation)
        cache.bump_generation(user.id)
        return conversation


    def delete_conversation(self, conversation_id: int, user: User, db: Session) -> dict:
        with cache.conversation_lock(user.id, conversation_id) as acquired:
            if not acquired:
                raise HTTPException(status_code=409, detail="This conversation is processing a message. Try again shortly.")
            return self._delete_conversation(conversation_id, user, db)


    def _delete_conversation(self, conversation_id: int, user: User, db: Session) -> dict:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        db.delete(conversation)
        db.commit()
        cache.bump_generation(user.id)
        return {"message": "Conversation deleted"}


    def clear_history(self, user: User, db: Session) -> dict:
        conversation_ids = [
            row[0]
            for row in db.query(Conversation.id)
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.id)
            .all()
        ]
        with ExitStack() as locks:
            for conversation_id in conversation_ids:
                acquired = locks.enter_context(cache.conversation_lock(user.id, conversation_id, blocking_timeout=0.1))
                if not acquired:
                    raise HTTPException(status_code=409, detail="A conversation is processing a message. Try again shortly.")

            conversations = (
                db.query(Conversation)
                .filter(Conversation.user_id == user.id)
                .all()
            )
            for conversation in conversations:
                db.delete(conversation)
            db.commit()
            cache.bump_generation(user.id)
            return {"message": "All conversations cleared"}
