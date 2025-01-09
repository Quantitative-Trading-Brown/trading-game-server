import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'lmao'
    DEBUG = os.environ.get('FLASK_DEBUG') or True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///game_data.sqlite'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = 'redis://localhost:6379/0'
