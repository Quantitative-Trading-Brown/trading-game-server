import json
from flask import Blueprint, request, jsonify
from flask_socketio import disconnect, join_room

from ..auth import tokens
from ..services import *

blueprint = Blueprint("connections", __name__)


@socketio.on("connect", namespace="/player")
def player_connect():
    # Extract token from the query parameters
    token = request.args.get("token")
    player_id = tokens.verify_token(token, "player")

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
    game_id = tokens.verify_token(token, "admin")

    if game_id is not None:
        join_room(game_id)
        r.hset("socket_admins", sid(request), game_id)
    else:
        disconnect()


@socketio.on("disconnect", namespace="/player")
def player_disconnect():
    player_id = r.hget("socket_users", sid(request))
    if player_id is None:
        return

    r.hdel(f"user:{player_id}", "sid")
    r.hdel("socket_users", sid(request))
