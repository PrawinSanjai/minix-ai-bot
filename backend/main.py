import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from config import Configuration
from middleware.security import (
    MetricsMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from sqlalchemy import text
from database import engine, Base
from apis.auth import router as auth_router
from apis.user import router as user_router
from apis.chat import router as chat_router
from services.cache import close_cache, initialize_cache
from services.observability import close_metrics, initialize_metrics, render_prometheus

config = Configuration()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis_limiter = None
    app.state.redis_events = None
    limiter = Redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        max_connections=100,
        socket_connect_timeout=1,
        socket_timeout=1,
        health_check_interval=30,
    )
    try:
        await limiter.ping()
        app.state.redis_limiter = limiter
        initialize_cache(config.REDIS_URL)
        app.state.redis_events = Redis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            max_connections=100,
            socket_connect_timeout=1,
            socket_timeout=None,
            health_check_interval=30,
        )
    except RedisError:
        logger.warning("Redis unavailable at startup; caching and shared rate limiting are disabled", exc_info=True)
        await limiter.aclose()
        app.state.redis_limiter = None

    initialize_metrics()
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        yield
    finally:
        close_cache()
        close_metrics()
        if app.state.redis_limiter is not None:
            await app.state.redis_limiter.aclose()
        if app.state.redis_events is not None:
            await app.state.redis_events.aclose()


api = FastAPI(title="minix-backend", docs_url="/docs", lifespan=lifespan)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
api.add_middleware(SecurityHeadersMiddleware)
api.add_middleware(MetricsMiddleware)
api.add_middleware(
    RequestSizeLimitMiddleware,
    max_body_bytes=config.MAX_REQUEST_BODY_BYTES,
)
api.add_middleware(
    RateLimitMiddleware,
    max_requests=config.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW_SECONDS,
)

api.include_router(auth_router)
api.include_router(user_router)
api.include_router(chat_router)


@api.get("/")
def home():
    return {"result": "success", "message": "Please Go To /Docs"}

@api.get("/health-check")
def healthcheck():
    return {
        "result": "success",
        "time": datetime.now(),
        "redis_available": api.state.redis_limiter is not None,
    }


@api.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")
