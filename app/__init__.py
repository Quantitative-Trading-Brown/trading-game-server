import socket, os
import firebase_admin
from firebase_admin import credentials, firestore

import logging
from flask import Flask
from flask_cors import CORS

from .blueprints import blueprints
from .services import *


def upload_address(app):
    cred = credentials.Certificate(
        os.path.join(app.instance_path, app.config["FIREBASE_CREDENTIALS"])
    )
    firebase_admin.initialize_app(cred)

    db = firestore.client()

    db.collection("servers").document(app.config["FIREBASE_DOC"]).set(
        {
            "name": app.config["FIREBASE_NAME"],
            "ip": app.config["FIREBASE_ADDRESS"],
        }
    )


def create_app(test_config=None):
    logging.getLogger("werkzeug").disabled = True

    app = Flask(__name__, instance_relative_config=True)

    app.config.from_pyfile("application.cfg")

    if app.config["FIREBASE_UPLOAD"]:
        upload_address(app)

    CORS(app, origins=app.config["CORS_ORIGINS"])

    socketio.init_app(app, cors_allowed_origins=app.config["CORS_ORIGINS"])

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    with app.app_context():
        r.flushall()

        if app.config["DEBUG"] and os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            from .overseer import game_manager

            game_id, code, _ = game_manager.create_game()
            print(code)

            from .state import states

            states.setup_to_live(game_id, "SP", True)

    return app
