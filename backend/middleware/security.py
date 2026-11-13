import logging
import asyncio
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from redis.exceptions import RedisError
from services import observability

logger = logging.getLogger(__name__)

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
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, self.window_seconds)
            ttl = await redis_client.ttl(key)
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
        response = await call_next(request)
        await asyncio.to_thread(observability.increment, f"http_responses_{response.status_code // 100}xx_total")
        return response
