import logging

from flask import Flask
from flask_cors import CORS
from .config import Config
from .model import socketio, r

def create_app(config_class=Config):
    logging.getLogger('werkzeug').disabled = True

    app = Flask(__name__)
    app.config.from_object(config_class)  # Load configuration from Config class
    CORS(app, origins=["http://localhost:3000", "https://simulator.qtab.site"])

    socketio.init_app(app)

    with app.app_context():
        r.flushall()

    from .login import login as login_blueprint
    app.register_blueprint(login_blueprint)

    from .game import game as game_blueprint
    app.register_blueprint(game_blueprint)

    from .trading import trading as trading_blueprint
    app.register_blueprint(trading_blueprint)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    return app
