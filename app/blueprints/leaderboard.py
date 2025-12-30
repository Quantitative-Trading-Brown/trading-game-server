from flask import Blueprint, request, jsonify
from typing import Awaitable, Any

from ..utils import helpers
from ..utils.services import *

leaderboard_manager = Blueprint("leaderboard_manager", __name__)

@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id, _ = helpers.identify(sid(request))

    results = extract(r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True))

    named_rankings = [
        (extract(r.hget(f"user:{pid}", "username")), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/admin", to=sid(request))


@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    game_id, player_id = helpers.identify(sid(request))

    results = extract(r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True))

    named_rankings = [
        (extract(r.hget(f"user:{pid}", "username")), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/player", to=sid(request))
