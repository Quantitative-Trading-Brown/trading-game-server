import logging
from flask import Flask
from flask_cors import CORS

from .utils.services import *

def create_app(test_config=None):
    logging.getLogger("werkzeug").disabled = True

    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config.from_pyfile("application.cfg")
    else:
        app.config.from_mapping(test_config)

    CORS(app, origins=app.config["CORS_ORIGINS"])

    socketio.init_app(app)

    with app.app_context():
        r.flushall()

    from .blueprints import lobby_manager

    app.register_blueprint(lobby_manager)

    from .blueprints import game_manager

    app.register_blueprint(game_manager)

    from .blueprints import snapshot_manager

    app.register_blueprint(snapshot_manager)

    from .blueprints import order_manager

    app.register_blueprint(order_manager)

    from .blueprints import socket_manager

    app.register_blueprint(socket_manager)

    from .blueprints import leaderboard_manager

    app.register_blueprint(leaderboard_manager)

    return app
