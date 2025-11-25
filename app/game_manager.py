import time
import json
from flask import Blueprint, request, jsonify
from typing import Awaitable, Any

from .utils import socketio, r, sid
from .tick import start_update_flusher
from .bot import start_bot
from .resolver import generate_rankings

game_manager = Blueprint("game_manager", __name__)

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
        r.hset(f"game:{game_id}:security:{sec_id}", "tick", "1")

    securities = r.smembers(f"game:{game_id}:securities")
    assert not isinstance(securities, Awaitable)

    security_props = {
        sec_id: r.hgetall(f"game:{game_id}:security:{sec_id}") for sec_id in securities
    }

    socketio.emit("securities_update", security_props, namespace="/admin", to=game_id)
    socketio.emit("securities_update", security_props, namespace="/player", to=game_id)

    set_state(game_id, 1)

    start_bot(game_id)
    start_update_flusher(game_id)


@socketio.on("endgame", namespace="/admin")
def endgame():
    game_id = int(r.hget("socket_admins", sid(request)))
    set_state(game_id, 2)


@socketio.on("rankgame", namespace="/admin")
def rankgame(true_prices={}):
    game_id = int(r.hget("socket_admins", sid(request)))

    for sec_id, price in true_prices.items():
        r.hset(f"game:{game_id}:true_prices", sec_id, price)
    r.hset(f"game:{game_id}:true_prices", "0", "1")

    generate_rankings(game_id)
    set_state(game_id, 3)

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
