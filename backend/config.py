from services.utils import get_env

class Configuration:
    DATABASE_URL = get_env("DATABASE_URL", default=None)
    MINIX_API_KEY = get_env("MINIX_API_KEY", default=None)