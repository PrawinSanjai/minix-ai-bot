"""Background worker for chat replies stored in PostgreSQL."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from redis import Redis
from sqlalchemy.orm import aliased

from config import Configuration
from database import db_session
from models import ChatJob, Conversation, Message, User
from services import cache, observability
from services.llm import LLMService
from services.rag import RAGService

logger = logging.getLogger(__name__)
config = Configuration()
llm_service = LLMService()
rag_service = RAGService()


def claim_next_job() -> int | None:
    """Claim the oldest job whose conversation has no earlier unfinished job."""
    db = db_session()
    older_job = aliased(ChatJob)
    try:
        earlier_unfinished = db.query(older_job.id).filter(
            older_job.conversation_id == ChatJob.conversation_id,
            older_job.id < ChatJob.id,
            older_job.status.in_(["queued", "processing"]),
        ).exists()
        job = (
            db.query(ChatJob)
            .filter(ChatJob.status == "queued", ~earlier_unfinished)
            .order_by(ChatJob.id.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job:
            return None
        job.status = "processing"
        job.attempts += 1
        job.error = None
        db.commit()
        return job.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def recover_stale_jobs(redis_client: Redis) -> None:
    """Retry jobs left processing after a worker exits."""
    db = db_session()
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=30)
    try:
        jobs = db.query(ChatJob).filter(
            ChatJob.status == "processing",
            ChatJob.updated_at < stale_before,
        ).with_for_update(skip_locked=True).all()
        for job in jobs:
            if job.attempts >= config.CHAT_JOB_MAX_ATTEMPTS:
                job.status = "failed"
                job.error = "Minix could not generate a reply. Please try again."
            else:
                job.status = "queued"
        db.commit()
        for job in jobs:
            if job.status == "failed":
                publish_event(redis_client, job.id, "failed", {
                    "status": "failed",
                    "error": job.error,
                })
    except Exception:
        db.rollback()
        logger.exception("Could not recover old chat jobs")
    finally:
        db.close()


def publish_event(redis_client: Redis, job_id: int, event_type: str, data: dict) -> None:
    try:
        key = f"minix:chat:job-events:{job_id}"
        redis_client.xadd(key, {"type": event_type, "data": json.dumps(data)}, maxlen=1000)
        redis_client.expire(key, 24 * 60 * 60)
    except RedisError:
        logger.warning("Could not publish chat event for job %s", job_id)


def retry_job(job_id: int, error: Exception, redis_client: Redis) -> None:
    db = db_session()
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).with_for_update().first()
        if not job or job.status in {"completed", "failed"}:
            return
        if job.attempts >= config.CHAT_JOB_MAX_ATTEMPTS:
            job.status = "failed"
            job.error = "Minix could not generate a reply. Please try again."
            status = "failed"
        else:
            job.status = "queued"
            job.error = None
            status = "retrying"
        db.commit()
        publish_event(redis_client, job_id, status, {
            "status": status,
            "error": job.error,
            "attempt": job.attempts,
        })
        if status == "failed":
            observability.increment("chat_jobs_failed_total")
    except Exception:
        db.rollback()
        logger.exception("Could not update failed chat job %s (%s)", job_id, type(error).__name__)
    finally:
        db.close()


def process_chat_job(job_id: int, redis_client: Redis) -> None:
    db = db_session()
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
        if not job:
            return
        user_id = job.user_id
        conversation_id = job.conversation_id
        user_message_id = job.user_message_id
        user_message = db.query(Message).filter(Message.id == user_message_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        if not user_message or not user:
            raise RuntimeError("Chat job data is incomplete")

        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.id != user_message_id,
        ).order_by(Message.id.asc()).all()
        history = rag_service.build_conversation_history(messages, max_turns=30)
        rag_context = rag_service.search_relevant_context(
            db, user_message.content, user_id, limit=5, exclude_message_id=user_message_id,
        )
        embedding = rag_service.generate_embedding(user_message.content)
        if embedding:
            rag_service.store_embedding(db, user_message_id, user_id, embedding)
        db.commit()
        message_text = user_message.content
        tone = user.tone
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    with cache.conversation_lock(user_id, conversation_id, blocking_timeout=1) as acquired:
        if not acquired:
            db = db_session()
            try:
                job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
                if job and job.status == "processing":
                    job.status = "queued"
                    db.commit()
            finally:
                db.close()
            return

        last_heartbeat = time.monotonic()

        def on_chunk(chunk: str) -> None:
            nonlocal last_heartbeat
            publish_event(redis_client, job_id, "chunk", {"text": chunk})
            if time.monotonic() - last_heartbeat > 30:
                heartbeat_db = db_session()
                try:
                    heartbeat_db.query(ChatJob).filter(
                        ChatJob.id == job_id,
                        ChatJob.status == "processing",
                    ).update(
                        {ChatJob.updated_at: datetime.now(timezone.utc)},
                    )
                    heartbeat_db.commit()
                    last_heartbeat = time.monotonic()
                except Exception:
                    heartbeat_db.rollback()
                    logger.warning("Could not update worker heartbeat for job %s", job_id)
                finally:
                    heartbeat_db.close()

        publish_event(redis_client, job_id, "processing", {"status": "processing"})
        reply, emotion = llm_service.stream_chat_response(
            user_message=message_text,
            tone=tone,
            conversation_history=history,
            rag_context=rag_context,
            on_chunk=on_chunk,
        )
        embedding = rag_service.generate_embedding(reply)

        db = db_session()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id).with_for_update().first()
            if not job or job.status != "processing":
                return
            bot_message = Message(conversation_id=conversation_id, role="bot", content=reply)
            db.add(bot_message)
            db.flush()
            if embedding:
                rag_service.store_embedding(db, bot_message.id, user_id, embedding)
            job.assistant_message_id = bot_message.id
            job.emotion = emotion
            job.status = "completed"
            job.error = None
            conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conversation:
                conversation.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    cache.bump_generation(user_id)
    observability.increment("chat_jobs_completed_total")
    publish_event(redis_client, job_id, "completed", {
        "status": "completed",
        "conversation_id": conversation_id,
        "reply": reply,
        "emotion": emotion,
    })


async def run_worker() -> None:
    sync_redis = Redis.from_url(config.REDIS_URL, decode_responses=True)
    observability.initialize_metrics()
    cache.initialize_cache(config.REDIS_URL)
    tasks: set[asyncio.Task] = set()
    last_recovery = 0.0

    async def run_job(job_id: int) -> None:
        try:
            await asyncio.to_thread(process_chat_job, job_id, sync_redis)
        except Exception as error:
            logger.exception("Chat job %s failed", job_id)
            await asyncio.to_thread(retry_job, job_id, error, sync_redis)

    try:
        await asyncio.to_thread(sync_redis.ping)
        while True:
            tasks = {task for task in tasks if not task.done()}
            if time.monotonic() - last_recovery > 60:
                await asyncio.to_thread(recover_stale_jobs, sync_redis)
                last_recovery = time.monotonic()

            capacity = max(config.CHAT_WORKER_CONCURRENCY - len(tasks), 0)
            job_id = None
            if capacity:
                job_id = await asyncio.to_thread(claim_next_job)
            if job_id is None:
                await asyncio.sleep(0.5)
                continue
            tasks.add(asyncio.create_task(run_job(job_id)))
    finally:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        sync_redis.close()
        cache.close_cache()
        observability.close_metrics()


if __name__ == "__main__":
    asyncio.run(run_worker())
