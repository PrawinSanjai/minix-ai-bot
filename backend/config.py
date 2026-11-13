from services.utils import get_env

class Configuration:
    SECRET_KEY = get_env("SECRET_KEY", default=None)
    DATABASE_URL = get_env("DATABASE_URL", default=None)
    MINIX_API_KEY = get_env("MINIX_API_KEY", default=None)
    CORS_ALLOW_ORIGINS = get_env("CORS_ALLOW_ORIGINS", default=None)
    RATE_LIMIT_WINDOW_SECONDS = int(get_env("RATE_LIMIT_WINDOW_SECONDS", default=60))
    RATE_LIMIT_MAX_REQUESTS = int(get_env("RATE_LIMIT_MAX_REQUESTS", default=120))
    MAX_REQUEST_BODY_BYTES = int(get_env("MAX_REQUEST_BODY_BYTES", default=25000))
    GEMINI_API_KEY = get_env("GEMINI_API_KEY", default=None)
    REDIS_URL = get_env("REDIS_URL", default="redis://localhost:6379/0")
    REDIS_CACHE_TTL_SECONDS = int(get_env("REDIS_CACHE_TTL_SECONDS", default=60))
    DB_POOL_SIZE = int(get_env("DB_POOL_SIZE", default=10))
    DB_MAX_OVERFLOW = int(get_env("DB_MAX_OVERFLOW", default=20))
    DB_POOL_TIMEOUT_SECONDS = int(get_env("DB_POOL_TIMEOUT_SECONDS", default=30))
    CHAT_JOB_MAX_ATTEMPTS = int(get_env("CHAT_JOB_MAX_ATTEMPTS", default=4))
    CHAT_WORKER_CONCURRENCY = int(get_env("CHAT_WORKER_CONCURRENCY", default=4))
