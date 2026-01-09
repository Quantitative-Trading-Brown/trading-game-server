from flask import Blueprint, request
from flask_socketio import disconnect, join_room

from app.services import *
from app.overseer import validation

blueprint = Blueprint("connections", __name__)


@socketio.on("connect", namespace="/player")
def player_connect():
    if game_id := validation.new_player_connection(request):
        join_room(game_id)
    else:
        disconnect()


@socketio.on("connect", namespace="/admin")
def admin_connect():
    if game_id := validation.new_admin_connection(request):
        join_room(game_id)
    else:
        disconnect()


@socketio.on("disconnect", namespace="/player")
def player_disconnect():
    player_id = r.hget("player_sockets", sid(request))
    if player_id is None:
        return

    r.hdel("player_sockets", sid(request))
    r.hdel(f"player:{player_id}", "sid")
