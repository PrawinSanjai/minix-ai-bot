"""Redis Streams consumer for durable, ordered chat generation jobs."""

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import BusyGroupError, RedisError
from sqlalchemy.orm import Session

from config import Configuration
from database import db_session
from models import ChatJob, Conversation, ConversationMemory, JobOutbox, Message, User
from services import cache, observability
from services.chat import llm_service, rag_service
from services.jobs import create_queue_client

logger = logging.getLogger(__name__)
config = Configuration()


def _publish_event(redis_client: Redis, job_id: int, event_type: str, data: dict) -> None:
    key = f"minix:chat:job-events:{job_id}"
    try:
        redis_client.xadd(
            key,
            {"type": event_type, "data": json.dumps(data, separators=(",", ":"))},
            maxlen=2000,
            approximate=True,
        )
        redis_client.expire(key, 24 * 60 * 60)
    except RedisError:
        # The job remains durable in PostgreSQL; clients can recover by polling status.
        logger.warning("Could not publish a live event for chat job %s", job_id, exc_info=True)


def _terminal_event(redis_client: Redis, job_id: int) -> None:
    db: Session = db_session()
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
        if not job:
            return
        if job.status == "completed":
            reply = db.query(Message.content).filter(Message.id == job.assistant_message_id).scalar() if job.assistant_message_id else ""
            _publish_event(redis_client, job.id, "completed", {
                "job_id": job.id,
                "conversation_id": job.conversation_id,
                "reply": reply or "",
                "emotion": job.emotion or "neutral",
                "status": job.status,
            })
        elif job.status == "failed":
            _publish_event(redis_client, job.id, "failed", {
                "job_id": job.id,
                "conversation_id": job.conversation_id,
                "status": job.status,
                "error": job.error or "The reply could not be generated.",
            })
    finally:
        db.close()


def _defer_job(job_id: int, delay_seconds: float = 1) -> None:
    db: Session = db_session()
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).with_for_update().first()
        if job and job.status == "queued":
            db.add(JobOutbox(
                job_id=job.id,
                available_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
            ))
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_retry_or_failed(job_id: int, exc: Exception, redis_client: Redis) -> None:
    db: Session = db_session()
    terminal = False
    attempt = 0
    conversation_id = None
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).with_for_update().first()
        if not job or job.status in {"completed", "failed"}:
            return
        if job.status == "queued":
            # Covers failures before process_chat_job could mark the attempt as
            # processing, so malformed records cannot retry forever.
            job.attempts += 1
        attempt = max(job.attempts, 1)
        conversation_id = job.conversation_id
        if attempt < config.CHAT_JOB_MAX_ATTEMPTS:
            delay = min(2 ** max(attempt - 1, 0), 30) + random.uniform(0, 0.5)
            job.status = "queued"
            job.error = None
            db.add(JobOutbox(job_id=job.id, available_at=datetime.now(timezone.utc) + timedelta(seconds=delay)))
        else:
            terminal = True
            job.status = "failed"
            job.error = "Minix could not generate a reply after several attempts. Please try again."
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if terminal:
        observability.increment("chat_jobs_failed_total")
        _publish_event(redis_client, job_id, "failed", {
            "job_id": job_id,
            "conversation_id": conversation_id,
            "status": "failed",
            "error": "Minix could not generate a reply after several attempts. Please try again.",
        })
        try:
            redis_client.xadd("minix:chat:jobs:dead-letter", {
                "job_id": str(job_id),
                "attempts": str(attempt),
                "error_type": type(exc).__name__,
            }, maxlen=10_000, approximate=True)
        except RedisError:
            logger.warning("Could not publish failed job %s to the dead-letter stream", job_id, exc_info=True)
    else:
        observability.increment("chat_jobs_retried_total")
        _publish_event(redis_client, job_id, "retrying", {"job_id": job_id, "attempt": attempt})


def process_chat_job(job_id: int, redis_client: Redis) -> None:
    started = time.monotonic()
    # Fetch ownership identifiers before taking the distributed conversation lock.
    db: Session = db_session()
    try:
        job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
        if not job:
            return
        user_id, conversation_id = job.user_id, job.conversation_id
        if job.status in {"completed", "failed"}:
            _terminal_event(redis_client, job_id)
            return
    finally:
        db.close()

    with cache.conversation_lock(user_id, conversation_id, blocking_timeout=0.1) as acquired:
        if not acquired:
            # Another worker is already handling this conversation. This stream
            # delivery is a duplicate or out of order; the active worker owns it.
            return

        db = db_session()
        try:
            job = db.query(ChatJob).filter(ChatJob.id == job_id).with_for_update().first()
            if not job:
                return
            if job.status in {"completed", "failed"}:
                db.close()
                _terminal_event(redis_client, job_id)
                return

            earlier_job = db.query(ChatJob.id).filter(
                ChatJob.conversation_id == job.conversation_id,
                ChatJob.id < job.id,
                ChatJob.status.in_(["queued", "processing"]),
            ).first()
            if earlier_job:
                db.close()
                _defer_job(job_id)
                return

            job.status = "processing"
            job.attempts += 1
            job.error = None
            db.commit()
            _publish_event(redis_client, job_id, "processing", {"job_id": job_id, "status": "processing"})

            job = db.query(ChatJob).filter(ChatJob.id == job_id).first()
            user = db.query(User).filter(User.id == user_id).first()
            conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            user_message = db.query(Message).filter(Message.id == job.user_message_id).first()
            if not user or not conversation or not user_message:
                raise RuntimeError("Chat job data is incomplete")

            messages = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .all()
            )
            history_messages = [message for message in messages if message.id != user_message.id]
            history = rag_service.build_conversation_history(history_messages, max_turns=30)
            rag_context = rag_service.search_relevant_context(
                db,
                user_message.content,
                user_id,
                limit=5,
                exclude_message_id=user_message.id,
            )

            user_embedding = rag_service.generate_embedding(user_message.content)
            if user_embedding:
                rag_service.store_embedding(db, user_message.id, user_id, user_embedding)

            memories = (
                db.query(ConversationMemory)
                .filter(
                    ConversationMemory.user_id == user_id,
                    ConversationMemory.conversation_id != conversation_id,
                )
                .order_by(ConversationMemory.updated_at.desc())
                .limit(5)
                .all()
            )
            if memories:
                memory_context = "\n\n".join(f"[Long-term memory]: {memory.summary}" for memory in memories)
                rag_context = f"{rag_context}\n\n{memory_context}" if rag_context else memory_context

            tone = user.tone
            message_text = user_message.content
            transcript = "\n".join(part for part in [history, f"User: {message_text}"] if part)
            user_count = sum(1 for message in messages if message.role == "user")
            old_memory = db.query(ConversationMemory).filter(
                ConversationMemory.conversation_id == conversation_id,
            ).first()
            old_summary = old_memory.summary if old_memory else ""
            if old_summary:
                rag_context = f"{rag_context}\n\n[Long-term memory]: {old_summary}" if rag_context else f"[Long-term memory]: {old_summary}"
            db.commit()
        finally:
            db.close()

        try:
            _publish_event(redis_client, job_id, "reset", {"job_id": job_id})

            last_heartbeat = time.monotonic()

            def on_chunk(chunk: str) -> None:
                nonlocal last_heartbeat
                _publish_event(redis_client, job_id, "chunk", {"text": chunk})
                if time.monotonic() - last_heartbeat >= 15:
                    heartbeat_db: Session = db_session()
                    try:
                        heartbeat_db.query(ChatJob).filter(
                            ChatJob.id == job_id,
                            ChatJob.status == "processing",
                        ).update(
                            {ChatJob.updated_at: datetime.now(timezone.utc)},
                            synchronize_session=False,
                        )
                        heartbeat_db.commit()
                        last_heartbeat = time.monotonic()
                    except Exception:
                        heartbeat_db.rollback()
                        logger.warning("Could not update heartbeat for chat job %s", job_id, exc_info=True)
                    finally:
                        heartbeat_db.close()

            reply, emotion = llm_service.stream_chat_response(
                user_message=message_text,
                tone=tone,
                conversation_history=history,
                rag_context=rag_context,
                on_chunk=on_chunk,
            )

            new_summary = old_summary
            if user_count and user_count % max(config.MEMORY_SUMMARY_EVERY, 1) == 0:
                try:
                    summary_transcript = f"{transcript}\nMinix: {reply}"
                    new_summary = llm_service.summarize_conversation(old_summary, summary_transcript)
                except Exception:
                    logger.warning("Could not update long-term memory for conversation %s", conversation_id, exc_info=True)

            bot_embedding = rag_service.generate_embedding(reply)
            db = db_session()
            try:
                job = db.query(ChatJob).filter(ChatJob.id == job_id).with_for_update().first()
                if not job:
                    return
                if job.status == "completed":
                    _terminal_event(redis_client, job_id)
                    return
                bot_message = Message(conversation_id=conversation_id, role="bot", content=reply)
                db.add(bot_message)
                db.flush()
                if bot_embedding:
                    rag_service.store_embedding(db, bot_message.id, user_id, bot_embedding)
                job.assistant_message_id = bot_message.id
                job.emotion = emotion
                job.status = "completed"
                job.error = None
                conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
                if conversation:
                    conversation.updated_at = datetime.now(timezone.utc)
                if new_summary and new_summary != old_summary:
                    memory = db.query(ConversationMemory).filter(
                        ConversationMemory.conversation_id == conversation_id,
                    ).first()
                    if memory:
                        memory.summary = new_summary
                        memory.updated_at = datetime.now(timezone.utc)
                    else:
                        db.add(ConversationMemory(
                            user_id=user_id,
                            conversation_id=conversation_id,
                            summary=new_summary,
                        ))
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

            cache.bump_generation(user_id)
            observability.increment("chat_jobs_completed_total")
            observability.observe_seconds("chat_job_duration_seconds", time.monotonic() - started)
            _publish_event(redis_client, job_id, "completed", {
                "job_id": job_id,
                "conversation_id": conversation_id,
                "status": "completed",
                "reply": reply,
                "emotion": emotion,
                "memory_updated": new_summary != old_summary,
            })
        except Exception as exc:
            logger.exception("Chat job %s failed on attempt %s", job_id, job.attempts)
            _mark_retry_or_failed(job_id, exc, redis_client)


async def _ensure_consumer_group(redis_client: AsyncRedis) -> None:
    try:
        await redis_client.xgroup_create(config.CHAT_JOB_STREAM, config.CHAT_JOB_GROUP, id="0-0", mkstream=True)
    except BusyGroupError:
        pass


async def run_worker() -> None:
    observability.initialize_metrics()
    sync_redis = create_queue_client()
    redis_client = AsyncRedis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        max_connections=max(config.CHAT_WORKER_CONCURRENCY * 4, 16),
        socket_connect_timeout=2,
        socket_timeout=None,
        health_check_interval=30,
    )
    consumer = f"{uuid.uuid4()}"
    try:
        await redis_client.ping()
        cache_ready = cache.initialize_cache(config.REDIS_URL)
        if not cache_ready:
            raise RuntimeError("Redis is required to run chat workers")
        await _ensure_consumer_group(redis_client)
    except Exception:
        await redis_client.aclose()
        sync_redis.close()
        cache.close_cache()
        observability.close_metrics()
        raise
    semaphore = asyncio.Semaphore(max(config.CHAT_WORKER_CONCURRENCY, 1))
    tasks: set[asyncio.Task] = set()

    async def handle_entry(entry_id: str, fields: dict[str, str]) -> None:
        async with semaphore:
            job_id = None
            try:
                job_id = int(fields["job_id"])
                await asyncio.to_thread(process_chat_job, job_id, sync_redis)
            except Exception as exc:
                logger.exception("Could not process Redis stream entry %s", entry_id)
                if job_id is None:
                    return
                try:
                    await asyncio.to_thread(_mark_retry_or_failed, job_id, exc, sync_redis)
                except Exception:
                    logger.exception("Could not schedule retry for chat job %s", job_id)
                    return
            try:
                await redis_client.xack(config.CHAT_JOB_STREAM, config.CHAT_JOB_GROUP, entry_id)
            except RedisError:
                logger.warning("Could not acknowledge Redis stream entry %s", entry_id, exc_info=True)

    try:
        while True:
            tasks.difference_update(task for task in tasks if task.done())
            capacity = max(config.CHAT_WORKER_CONCURRENCY - len(tasks), 0)
            if capacity:
                try:
                    reclaimed = await redis_client.xautoclaim(
                        config.CHAT_JOB_STREAM,
                        config.CHAT_JOB_GROUP,
                        consumer,
                        min_idle_time=max(config.CHAT_JOB_RECLAIM_IDLE_MS, 300_000),
                        start_id="0-0",
                        count=capacity,
                    )
                    for entry_id, fields in reclaimed[1]:
                        task = asyncio.create_task(handle_entry(entry_id, fields))
                        tasks.add(task)
                        capacity -= 1
                except RedisError:
                    logger.warning("Could not reclaim pending chat jobs", exc_info=True)

            if capacity:
                try:
                    batches = await redis_client.xreadgroup(
                        config.CHAT_JOB_GROUP,
                        consumer,
                        {config.CHAT_JOB_STREAM: ">"},
                        count=capacity,
                        block=1000,
                    )
                except RedisError:
                    logger.warning("Redis Streams unavailable; worker will reconnect", exc_info=True)
                    await asyncio.sleep(1)
                    continue
                for _, entries in batches:
                    for entry_id, fields in entries:
                        task = asyncio.create_task(handle_entry(entry_id, fields))
                        tasks.add(task)
    finally:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await redis_client.aclose()
        sync_redis.close()
        cache.close_cache()
        observability.close_metrics()


if __name__ == "__main__":
    asyncio.run(run_worker())
