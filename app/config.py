import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "lmao"
    DEBUG = os.environ.get("FLASK_DEBUG") or True
    REDIS_URL = "redis://localhost:6379/0"
