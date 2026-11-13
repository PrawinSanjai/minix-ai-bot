"""Small Redis cache for per-user conversation reads.

Redis is an acceleration layer only: cache errors fall back to PostgreSQL. A
per-user generation makes invalidation atomic across app workers and prevents a
read started before a write from repopulating the active cache namespace.
"""

import json
import logging
from contextlib import contextmanager

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
_client: Redis | None = None


def initialize_cache(redis_url: str) -> bool:
    global _client
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=1,
        socket_timeout=0.25,
        health_check_interval=30,
    )
    try:
        client.ping()
    except RedisError:
        client.close()
        _client = None
        logger.warning("Redis cache is unavailable; conversation reads will use PostgreSQL")
        return False
    _client = client
    return True


def close_cache() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _generation_key(user_id: int) -> str:
    return f"minix:chat:generation:{user_id}"


def generation(user_id: int) -> int:
    if _client is None:
        return 0
    try:
        return int(_client.get(_generation_key(user_id)) or 0)
    except (RedisError, TypeError, ValueError):
        logger.debug("Redis generation lookup failed", exc_info=True)
        return 0


def bump_generation(user_id: int) -> None:
    if _client is None:
        return
    try:
        _client.incr(_generation_key(user_id))
        _client.expire(_generation_key(user_id), 30 * 24 * 60 * 60)
    except RedisError:
        logger.debug("Redis cache invalidation failed", exc_info=True)


@contextmanager
def conversation_lock(user_id: int, conversation_id: int, blocking_timeout: float = 20):
    """Serialize writes to one conversation across workers when Redis is up."""
    if _client is None:
        yield True
        return

    lock = _client.lock(
        f"minix:chat:lock:{user_id}:{conversation_id}",
        timeout=300,
        blocking_timeout=blocking_timeout,
    )
    try:
        acquired = lock.acquire(blocking=True)
    except RedisError:
        logger.debug("Redis conversation lock unavailable; continuing without lock", exc_info=True)
        yield True
        return

    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except RedisError:
                logger.debug("Could not release Redis conversation lock", exc_info=True)


def get_json(key: str):
    if _client is None:
        return None
    try:
        value = _client.get(key)
        return json.loads(value) if value else None
    except (RedisError, ValueError):
        logger.debug("Redis cache read failed", exc_info=True)
        return None


def set_json(key: str, value, ttl_seconds: int) -> None:
    if _client is None:
        return
    try:
        _client.setex(key, ttl_seconds, json.dumps(value, separators=(",", ":")))
    except (RedisError, TypeError, ValueError):
        logger.debug("Redis cache write failed", exc_info=True)
