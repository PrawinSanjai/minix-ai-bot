"""Redis-backed counters and histograms shared by API and worker processes."""

import logging

from redis import Redis
from redis.exceptions import RedisError

from config import Configuration

logger = logging.getLogger(__name__)
config = Configuration()
_client: Redis | None = None
_METRICS_KEY = "minix:observability:metrics"
_LATENCY_BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)


def initialize_metrics() -> None:
    global _client
    _client = Redis.from_url(config.REDIS_URL, decode_responses=True, max_connections=10, socket_timeout=0.5)


def close_metrics() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def increment(name: str, amount: int = 1) -> None:
    if _client is None:
        return
    try:
        _client.hincrby(_METRICS_KEY, f"counter:{name}", amount)
        _client.expire(_METRICS_KEY, 7 * 24 * 60 * 60)
    except RedisError:
        logger.debug("Metric increment failed", exc_info=True)


def observe_seconds(name: str, value: float) -> None:
    if _client is None:
        return
    try:
        pipe = _client.pipeline(transaction=False)
        pipe.hincrby(_METRICS_KEY, f"histogram:{name}:count", 1)
        pipe.hincrbyfloat(_METRICS_KEY, f"histogram:{name}:sum", value)
        for bucket in _LATENCY_BUCKETS:
            if value <= bucket:
                pipe.hincrby(_METRICS_KEY, f"histogram:{name}:bucket:{bucket}", 1)
        pipe.hincrby(_METRICS_KEY, f"histogram:{name}:bucket:+Inf", 1)
        pipe.execute()
        _client.expire(_METRICS_KEY, 7 * 24 * 60 * 60)
    except RedisError:
        logger.debug("Metric observation failed", exc_info=True)


def render_prometheus() -> str:
    if _client is None:
        return "# metrics unavailable: Redis is not configured\n"
    try:
        values = _client.hgetall(_METRICS_KEY)
    except RedisError:
        return "# metrics unavailable: Redis is not reachable\n"

    lines = []
    for field, value in sorted(values.items()):
        parts = field.split(":")
        if parts[0] == "counter":
            lines.append(f"minix_{parts[1]} {value}")
        elif parts[0] == "histogram":
            name = parts[1]
            metric, *rest = parts[2:]
            if metric == "count":
                lines.append(f"minix_{name}_count {value}")
            elif metric == "sum":
                lines.append(f"minix_{name}_sum {value}")
            elif metric == "bucket":
                bucket = rest[0]
                lines.append(f'minix_{name}_bucket{{le="{bucket}"}} {value}')
    return "\n".join(lines) + "\n"
