import logging

from flask import Flask
from flask_cors import CORS
from .config import Config
from .model import db, socketio, redis_client

def create_app(config_class=Config):
    logging.getLogger('werkzeug').disabled = True

    app = Flask(__name__)
    app.config.from_object(config_class)  # Load configuration from Config class

    CORS(app, origins=["http://localhost:3000"])

    socketio.init_app(app)
    db.init_app(app)
    redis_client.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.commit()

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .game import game as game_blueprint
    app.register_blueprint(game_blueprint)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    return app
