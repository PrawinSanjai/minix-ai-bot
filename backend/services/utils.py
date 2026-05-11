import os
from dotenv import load_dotenv

load_dotenv()

def get_env(env_var: str, default=None):
    val = os.getenv(env_var)
    if val is None:
        return default
    return val