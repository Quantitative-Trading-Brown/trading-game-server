from flask import Blueprint, request, jsonify
from typing import Awaitable, Any

from .constants import socketio, r, sid

leaderboard = Blueprint("leaderboard", __name__)


def generate_rankings(game_id):
    true_prices = r.hgetall(f"game:{game_id}:true_prices")
    players = r.zrangebyscore(f"game:{game_id}:users", 0, 0)
    assert not isinstance(players, Awaitable)
    assert not isinstance(true_prices, Awaitable)

    for player_id in players:
        player_inv = r.hgetall(f"user:{player_id}:inventory")
        assert not isinstance(player_inv, Awaitable)

        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])
        r.zadd(f"game:{game_id}:users", {str(player_id): round(score, 2)})
    return r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)


@socketio.on("leaderboard", namespace="/admin")
def admin_leaderboard():
    game_id = int(r.hget("socket_admins", sid(request)))

    results = r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)
    assert not isinstance(results, Awaitable)

    named_rankings = [
        (r.hget(f"user:{pid}", "username"), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/admin", to=sid(request))


@socketio.on("leaderboard", namespace="/player")
def player_leaderboard():
    player_id = int(r.hget("socket_users", sid(request)))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))
    results = r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)
    assert not isinstance(results, Awaitable)

    named_rankings = [
        (r.hget(f"user:{pid}", "username"), score) for pid, score in results
    ]
    socketio.emit("leaderboard", named_rankings, namespace="/player", to=sid(request))
