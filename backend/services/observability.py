"""Small shared request and job counters stored in Redis."""

from redis import Redis
from redis.exceptions import RedisError

from config import Configuration

config = Configuration()
client: Redis | None = None
KEY = "minix:metrics"


def initialize_metrics() -> None:
    global client
    client = Redis.from_url(config.REDIS_URL, decode_responses=True, socket_timeout=1)


def close_metrics() -> None:
    global client
    if client is not None:
        client.close()
        client = None


def increment(name: str) -> None:
    if client is None:
        return
    try:
        client.hincrby(KEY, name, 1)
    except RedisError:
        pass


def render_prometheus() -> str:
    if client is None:
        return "# metrics unavailable\n"
    try:
        counts = client.hgetall(KEY)
        return "".join(f"minix_{name} {count}\n" for name, count in counts.items())
    except RedisError:
        return "# metrics unavailable\n"
