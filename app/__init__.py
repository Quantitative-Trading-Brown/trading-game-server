import logging
from flask import Flask
from flask_cors import CORS

from .blueprints import blueprints
from .services import *

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

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
