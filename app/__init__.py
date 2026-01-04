import socket, os
import firebase_admin
from firebase_admin import credentials, firestore

import logging
from flask import Flask
from flask_cors import CORS

from .blueprints import blueprints
from .services import *


def upload_local_ip(app):
    cred = credentials.Certificate(
        os.path.join(app.instance_path, app.config["FIREBASE_CREDENTIALS"])
    )
    firebase_admin.initialize_app(cred)

    db = firestore.client()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()

    db.collection("servers").document(app.config["FIREBASE_DOC"]).set(
        {
            "name": app.config["FIREBASE_NAME"],
            "ip": "http://" + local_ip,
        }
    )


def create_app(test_config=None):
    logging.getLogger("werkzeug").disabled = True

    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config.from_pyfile("application.cfg")
    else:
        app.config.from_mapping(test_config)

    CORS(app, origins=app.config["CORS_ORIGINS"])

    upload_local_ip(app)
    socketio.init_app(app, cors_allowed_origins=app.config["CORS_ORIGINS"])

    with app.app_context():
        r.flushall()

    for blueprint in blueprints:
        app.register_blueprint(blueprint)

    return app
