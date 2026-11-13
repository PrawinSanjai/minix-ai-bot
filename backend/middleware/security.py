import logging
import re
import time
import asyncio
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from redis.exceptions import RedisError
from services import observability

logger = logging.getLogger(__name__)

RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        try:
            is_too_large = content_length and int(content_length) > self.max_body_bytes
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header."},
            )

        if is_too_large:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body is too large."},
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int, window_seconds: int):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in {"/", "/health-check", "/docs", "/openapi.json"}:
            return await call_next(request)

        redis_client = getattr(request.app.state, "redis_limiter", None)
        if redis_client is None:
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        key = f"minix:rate:{client_host}:{request.method}:{request.url.path}"
        try:
            count, ttl = await redis_client.eval(RATE_LIMIT_SCRIPT, 1, key, self.window_seconds)
            count = int(count)
            ttl = int(ttl)
        except (RedisError, TypeError, ValueError):
            logger.debug("Redis rate limiter unavailable; allowing request", exc_info=True)
            return await call_next(request)

        if count > self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(max(ttl, 1))},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_name = re.sub(r"[^a-zA-Z0-9_]", "_", getattr(route, "path", "unmatched").strip("/")) or "root"
        await asyncio.to_thread(observability.increment, f"http_requests_{response.status_code // 100}xx_total")
        await asyncio.to_thread(
            observability.observe_seconds,
            f"http_{route_name}_duration_seconds",
            time.perf_counter() - started,
        )
        return response
