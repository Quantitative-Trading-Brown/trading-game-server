from flask import Blueprint, request
from typing import Awaitable, Any
import json

from .utils import socketio, r, sid

snapshot_manager = Blueprint("snapshot_manager", __name__)

def make_snapshot(game_id, player_id=None):
    securities = r.smembers(f"game:{game_id}:securities")
    assert not isinstance(securities, Awaitable)

    orderbooks = {
        sec_id: r.hgetall(f"game:{game_id}:security:{sec_id}:orderbook")
        for sec_id in securities
    }
    security_props = {
        sec_id: r.hgetall(f"game:{game_id}:security:{sec_id}") for sec_id in securities
    }

    raw_news = r.lrange(f"game:{game_id}:news", 0, 19)
    assert not isinstance(raw_news, Awaitable)

    past_news = [
        [json.loads(raw)["timestamp"], json.loads(raw)["message"]]
        for raw in reversed(raw_news)
    ]

    snapshot = {
        "game_state": r.get(f"game:{game_id}:state"),
        "game_props": r.hgetall(f"game:{game_id}"),
        "securities": security_props,
        "orderbooks": orderbooks,
        "past_news": past_news,
    }

    if player_id:
        orders = r.smembers(f"user:{player_id}:orders")
        assert not isinstance(orders, Awaitable)

        snapshot["username"] = r.hget(f"user:{player_id}", "username")
        snapshot["inventory"] = r.hgetall(f"user:{player_id}:inventory")
        snapshot["orders"] = {o: r.hgetall(f"game:{game_id}:order:{o}") for o in orders}

    return snapshot


@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    game_id = int(r.hget("socket_admins", sid(request)))

    socketio.emit(
        "snapshot", make_snapshot(game_id), namespace="/admin", to=sid(request)
    )


@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    player_id = int(r.hget("socket_users", sid(request)))
    game_id = int(r.hget(f"user:{player_id}", "game_id"))

    socketio.emit(
        "snapshot",
        make_snapshot(game_id, player_id),
        namespace="/player",
        to=sid(request),
    )
