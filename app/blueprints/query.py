from flask import Blueprint, request
from typing import Awaitable, Any
import json

from ..auth import identity
from ..control import snapshot
from ..services import *

blueprint = Blueprint("query", __name__)

@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    game_id, _ = identity.identify(sid(request))

    socketio.emit(
        "snapshot", snapshot.make_snapshot(game_id), namespace="/admin", to=sid(request)
    )


@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    game_id, player_id = identity.identify(sid(request))

    socketio.emit(
        "snapshot",
        snapshot.make_snapshot(game_id, player_id),
        namespace="/player",
        to=sid(request),
    )

@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id, _ = identity.identify(sid(request))

    results = extract(r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True))

    named_rankings = [
        (extract(r.hget(f"user:{pid}", "username")), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/admin", to=sid(request))


@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    game_id, player_id = identity.identify(sid(request))

    results = extract(r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True))

    named_rankings = [
        (extract(r.hget(f"user:{pid}", "username")), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/player", to=sid(request))
