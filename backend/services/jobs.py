"""PostgreSQL outbox publisher for the Redis Streams chat worker queue."""

import logging
import asyncio
from datetime import datetime, timezone

from redis import Redis
from sqlalchemy.orm import Session

from config import Configuration
from database import db_session
from models import ChatJob, JobOutbox
from redis.exceptions import RedisError
from services import observability

logger = logging.getLogger(__name__)
config = Configuration()


def create_queue_client() -> Redis:
    return Redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=1,
        socket_timeout=2,
        health_check_interval=30,
    )


def publish_pending_jobs(redis_client: Redis, batch_size: int = 100) -> int:
    """Publish committed outbox rows; duplicate stream entries are safe to replay."""
    published = 0
    now = datetime.now(timezone.utc)
    db: Session = db_session()
    try:
        rows = (
            db.query(JobOutbox)
            .join(ChatJob, ChatJob.id == JobOutbox.job_id)
            .filter(
                JobOutbox.published_at.is_(None),
                JobOutbox.available_at <= now,
                ChatJob.status == "queued",
            )
            .order_by(JobOutbox.id.asc())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
            .all()
        )
        for row in rows:
            redis_client.xadd(
                config.CHAT_JOB_STREAM,
                {"job_id": str(row.job_id)},
                maxlen=100_000,
                approximate=True,
            )
            row.published_at = now
            row.job.enqueued_at = now
            published += 1
        db.commit()
        return published
    except Exception:
        db.rollback()
        logger.exception("Could not publish chat jobs from the outbox")
        raise
    finally:
        db.close()


def reset_stale_jobs(redis_client: Redis, stale_after_seconds: int = 300, batch_size: int = 100) -> int:
    """Requeue jobs left processing by a worker that exited unexpectedly."""
    from datetime import timedelta

    stale_before = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    orphan_before = datetime.now(timezone.utc) - timedelta(seconds=config.CHAT_JOB_ORPHAN_SECONDS)
    now = datetime.now(timezone.utc)
    db: Session = db_session()
    reset = 0
    try:
        jobs = (
            db.query(ChatJob)
            .filter(ChatJob.status == "processing", ChatJob.updated_at < stale_before)
            .order_by(ChatJob.id.asc())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
            .all()
        )
        for job in jobs:
            if job.attempts >= config.CHAT_JOB_MAX_ATTEMPTS:
                job.status = "failed"
                job.error = "The reply worker stopped unexpectedly too many times. Please try again."
                redis_client.xadd(
                    f"minix:chat:job-events:{job.id}",
                    {"type": "failed", "data": '{"status":"failed","error":"The reply worker stopped unexpectedly too many times. Please try again."}'},
                    maxlen=2000,
                    approximate=True,
                )
            else:
                job.status = "queued"
                db.add(JobOutbox(job_id=job.id, available_at=now))
            reset += 1
        orphaned = (
            db.query(ChatJob)
            .filter(ChatJob.status == "queued", ChatJob.enqueued_at < orphan_before)
            .order_by(ChatJob.id.asc())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
            .all()
        )
        for job in orphaned:
            job.enqueued_at = now
            db.add(JobOutbox(job_id=job.id, available_at=now))
            reset += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not requeue stale chat jobs")
        raise
    finally:
        db.close()
    return reset


async def outbox_publisher_loop(redis_client: Redis) -> None:
    iteration = 0
    retry_delay = 0.5
    while True:
        try:
            await asyncio.to_thread(publish_pending_jobs, redis_client)
            iteration += 1
            if iteration % 60 == 0:
                await asyncio.to_thread(reset_stale_jobs, redis_client)
            retry_delay = 0.5
        except RedisError:
            logger.warning("Redis Streams unavailable; pending chat jobs remain in the PostgreSQL outbox")
            retry_delay = min(retry_delay * 2, 30)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Chat outbox publisher failed")
        await asyncio.sleep(retry_delay)
