from flask import Blueprint, request, jsonify
from typing import Awaitable, Any

from ..utils.socketio import socketio, sid
from ..utils.storage import r, extract

leaderboard_manager = Blueprint("leaderboard_manager", __name__)

@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id = int(extract(r.hget("socket_admins", sid(request))))

    results = extract(r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True))

    named_rankings = [
        (extract(r.hget(f"user:{pid}", "username")), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/admin", to=sid(request))


@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    player_id = int(extract(r.hget("socket_users", sid(request))))
    game_id = int(extract(r.hget(f"user:{player_id}", "game_id")))

    results = extract(r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True))

    named_rankings = [
        (extract(r.hget(f"user:{pid}", "username")), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/player", to=sid(request))
