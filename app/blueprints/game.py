import time, json, os, sys

from flask import Blueprint, request, jsonify, current_app

from .. import clock

from ..utils.services import *
from ..utils import helpers

from ..setup import GameSetup


game_manager = Blueprint("game_manager", __name__)


@socketio.on("querypresets", namespace="/admin")
def query_presets():
    with open(os.path.join(current_app.instance_path, "presets.json"), "r") as f:
        data = json.load(f)

    presets = [
        {"id": preset_id, "name": d.get("name"), "desc": d.get("description")}
        for (preset_id, d) in data.items()
    ]
    socketio.emit(
        "presets",
        presets,
        namespace="/admin",
        to=sid(request),
    )


@socketio.on("startgame", namespace="/admin")
def start_game(preset):
    game_id, _ = helpers.identify(sid(request))

    with open(os.path.join(current_app.instance_path, "presets.json"), "r") as f:
        data = json.load(f).get(preset)

    if data is None:
        socketio.emit(
            "error",
            f"Preset '{preset}' not found.",
            namespace="/admin",
            to=sid(request),
        )
        return

    setup = GameSetup(os.path.join(current_app.instance_path, "presets", data["file"]))

    # Apply settings to Redis and notify clients on SocketIO
    setup.apply(game_id)

    helpers.set_state(game_id, 1)
    clock.clock_start(game_id, setup)


@socketio.on("endgame", namespace="/admin")
def end_game():
    game_id, _ = helpers.identify(sid(request))
    helpers.set_state(game_id, 2)


@socketio.on("rankgame", namespace="/admin")
def rank_game(true_prices={}):
    game_id, _ = helpers.identify(sid(request))

    for sec_id, price in true_prices.items():
        r.hset(f"game:{game_id}:true_prices", sec_id, price)

    # Set value of cash (asset id 0) to 1
    r.hset(f"game:{game_id}:true_prices", "USD", "1")

    helpers.generate_rankings(game_id)
    helpers.set_state(game_id, 3)


@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    """Broadcast a message to all connected clients and save it in Valkey."""
    game_id, _ = helpers.identify(sid(request))
    news_key = f"game:{game_id}:news"

    entry = {
        "timestamp": time.strftime("%H:%M:%S", time.localtime()),
        "message": "[news] " + message,
    }

    r.lpush(news_key, json.dumps(entry))
    r.ltrim(news_key, 0, 99)

    # Broadcast to admins and players
    socketio.emit(
        "news", [entry["timestamp"], entry["message"]], namespace="/admin", to=game_id
    )
    socketio.emit(
        "news", [entry["timestamp"], entry["message"]], namespace="/player", to=game_id
    )
