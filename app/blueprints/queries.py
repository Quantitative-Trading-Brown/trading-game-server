"""
SocketIO event handlers for querying presets, snapshots, and leaderboards.

presets: Emits a list of available presets to the admin client.
snapshot: Emits a game snapshot to the admin/player client.
leaderboard: Emits the game leaderboard to the admin/player client.
"""

import json, os
from flask import Blueprint, request

from app.services import *
from app.overseer import identity
from app.communication import snapshot
from app.state import setup, results

blueprint = Blueprint("queries", __name__)


@socketio.on("presets", namespace="/admin")
def query_presets():
    socketio.emit(
        "presets",
        setup.get_presets(),
        namespace="/admin",
        to=sid(request),
    )


@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    game_id, _ = identity.identify(sid(request))
    socketio.emit(
        "snapshot", snapshot.get_snapshot(game_id), namespace="/admin", to=sid(request)
    )


@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    game_id, player_id = identity.identify(sid(request))
    socketio.emit(
        "snapshot",
        snapshot.get_snapshot(game_id, player_id),
        namespace="/player",
        to=sid(request),
    )


@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id, _ = identity.identify(sid(request))
    socketio.emit(
        "leaderboard",
        results.get_leaderboard(game_id),
        namespace="/admin",
        to=sid(request),
    )


@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    game_id, _ = identity.identify(sid(request))
    socketio.emit(
        "leaderboard",
        results.get_leaderboard(game_id),
        namespace="/player",
        to=sid(request),
    )
