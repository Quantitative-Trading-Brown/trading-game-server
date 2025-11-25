import logging

from flask import Flask
from flask_cors import CORS
from .config import Config
from .utils import socketio, r

def create_app(config_class=Config):
    logging.getLogger('werkzeug').disabled = True

    app = Flask(__name__)
    app.config.from_object(config_class)  # Load configuration from Config class
    CORS(app, origins=["http://localhost:3000", "https://simulator.qtab.site"])

    socketio.init_app(app)

    with app.app_context():
        r.flushall()

    from .lobby_manager import lobby_manager as lobby_blueprint
    app.register_blueprint(lobby_blueprint)

    from .game_manager import game_manager as game_blueprint
    app.register_blueprint(game_blueprint)

    from .snapshot_manager import snapshot_manager as snapshot_blueprint
    app.register_blueprint(snapshot_blueprint)

    from .order_manager import order_manager as order_blueprint
    app.register_blueprint(order_blueprint)

    from .socket_manager import socket_manager as socket_blueprint
    app.register_blueprint(socket_blueprint)

    return app
