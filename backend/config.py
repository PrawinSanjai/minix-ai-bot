from services.utils import get_env

class Configuration:
    DATABASE_URL = get_env("DATABASE_URL", default=None)
    MINIX_API_KEY = get_env("MINIX_API_KEY", default=None)
    CORS_ALLOW_ORIGINS = get_env("CORS_ALLOW_ORIGINS", default=None)
    RATE_LIMIT_WINDOW_SECONDS = get_env("RATE_LIMIT_WINDOW_SECONDS", default=60)
    RATE_LIMIT_MAX_REQUESTS = get_env("RATE_LIMIT_MAX_REQUESTS", default=120)
    MAX_REQUEST_BODY_BYTES = get_env("MAX_REQUEST_BODY_BYTES", default=25000)