from flask import Blueprint, request, jsonify

from app.services import *
from app.overseer import game_manager, validation

blueprint = Blueprint("overseer", __name__)


# Check if the service is up
@blueprint.route("/", methods=["GET"])
def test():
    return "", 204


# This acts as a soft auth check on the frontend to see if a redirect is necessary
@blueprint.route("/auth", methods=["POST"])
def check_auth():
    if auth_type := validation.check_auth(request.json) is not None:
        return jsonify({"type": auth_type}), 201
    else:
        return jsonify({"error": "Invalid token"}), 404


@blueprint.route("/create-game", methods=["POST"])
def create_game():
    game_id, code, admin_token = game_manager.create_game()
    return jsonify({"code": code, "token": admin_token}), 201


@blueprint.route("/join-game", methods=["POST"])
def join_game():
    status, content = game_manager.join_game(request.json)
    if status:
        return jsonify({"message": "Joined successfully", "token": content}), 200
    else:
        return jsonify({"error": content}), 400
