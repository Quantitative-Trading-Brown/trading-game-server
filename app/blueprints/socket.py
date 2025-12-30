import json
from flask import Blueprint, request, jsonify
from flask_socketio import disconnect, join_room

from ..utils.socketio import socketio, sid
from ..utils.storage import r, extract
from ..utils.tokens import verify_token

socket_manager = Blueprint("socket_manager", __name__)


# This acts as a soft auth check on the frontend to see if a redirect is necessary
@socket_manager.route("/auth", methods=["POST"])
def checkAuth():
    data = request.json
    if not data:
        return jsonify({"error": "Invalid token"}), 404

    token = data["token"]

    verify_player = verify_token(token, "player")
    if verify_player is not None:
        return jsonify({"type": "player"}), 201

    verify_admin = verify_token(token, "admin")
    if verify_admin is not None:
        return jsonify({"type": "admin"}), 201

    return jsonify({"error": "Invalid token"}), 404


@socketio.on("connect", namespace="/player")
def player_connect():
    # Extract token from the query parameters
    token = request.args.get("token")
    player_id = verify_token(token, "player")

    if player_id is not None:
        game_id = int(extract(r.hget(f"user:{player_id}", "game_id")))

        join_room(game_id)
        r.hset("socket_users", sid(request), player_id)
        r.hset(f"user:{player_id}", "sid", sid(request))
    else:
        disconnect()


@socketio.on("connect", namespace="/admin")
def admin_connect():
    # Extract token from the query parameters
    token = request.args.get("token")
    game_id = verify_token(token, "admin")

    if game_id is not None:
        join_room(game_id)
        r.hset("socket_admins", sid(request), game_id)
    else:
        disconnect()


@socketio.on("disconnect", namespace="/player")
def player_disconnect():
    player_id = int(extract(r.hget("socket_users", sid(request))))
    r.hdel(f"user:{player_id}", "sid")
    r.hdel("socket_users", sid(request))
