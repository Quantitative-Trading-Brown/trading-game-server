import time
import json
from flask import Blueprint, request, jsonify
from typing import Awaitable, Any

from .constants import socketio, r, sid
from .tick import start_update_flusher
from .bot import start_bot
from .resolution import generate_rankings

game = Blueprint("game", __name__)

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


@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients and save it in Valkey."""
    game_id = int(r.hget("socket_admins", sid(request)))
    key = f"game:{game_id}:news"

    # Build entry
    entry = {
        "timestamp": time.strftime("%H:%M:%S", time.localtime()),
        "message": "[news] " + message,
    }

    # Save into Valkey list (latest first)
    r.lpush(key, json.dumps(entry))

    # Optionally trim to keep only last 100 messages
    r.ltrim(key, 0, 99)

    # Broadcast to admins and players
    socketio.emit(
        "news", [entry["timestamp"], entry["message"]], namespace="/admin", to=game_id
    )
    socketio.emit(
        "news", [entry["timestamp"], entry["message"]], namespace="/player", to=game_id
    )


def set_state(game_id, state):
    r.set(f"game:{game_id}:state", state)

    socketio.emit("gamestate_update", state, namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, namespace="/player", to=game_id)


@socketio.on("startgame", namespace="/admin")
def startgame(settings={}):
    game_id = int(r.hget("socket_admins", sid(request)))  # ty: ignore[unresolved-attribute]

    r.set(f"game:{game_id}:timestart", int(time.time()))

    for security in settings["securities"]:
        sec_id = security["id"]
        r.sadd(f"game:{game_id}:securities", sec_id)
        r.hset(f"game:{game_id}:security:{sec_id}", "name", security["name"])
        r.hset(f"game:{game_id}:security:{sec_id}", "tick", security["tick"])

    securities = r.smembers(f"game:{game_id}:securities")
    assert not isinstance(securities, Awaitable)

    security_props = {
        sec_id: r.hgetall(f"game:{game_id}:security:{sec_id}") for sec_id in securities
    }

    socketio.emit("securities_update", security_props, namespace="/admin", to=game_id)
    socketio.emit("securities_update", security_props, namespace="/player", to=game_id)

    set_state(game_id, 1)

    start_update_flusher(game_id)
    start_bot(game_id)


@socketio.on("endgame", namespace="/admin")
def endgame():
    game_id = int(r.hget("socket_admins", sid(request)))
    set_state(game_id, 2)


@socketio.on("rankgame", namespace="/admin")
def rankgame(true_prices={}):
    game_id = int(r.hget("socket_admins", sid(request)))

    for sec_id, price in true_prices.items():
        r.hset(f"game:{game_id}:true_prices", sec_id, price)
    r.hset(f"game:{game_id}:true_prices", 0, 1)

    generate_rankings(game_id)
    set_state(game_id, 3)
