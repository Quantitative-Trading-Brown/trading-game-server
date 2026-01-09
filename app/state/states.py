from enum import IntEnum
import os, json

from app.services import *
from app.state import setup, live, settlement, results


class State(IntEnum):
    SETUP = 0
    LIVE = 1
    SETTLEMENT = 2
    RESULTS = 3


def get_state(game_id: str) -> int:
    return int(extract(r.hget(f"game:{game_id}", "state")))


def set_state(game_id: str, state: int) -> None:
    # Update in Redis backend
    r.hset(f"game:{game_id}", "state", str(state))

    # Notify all clients about the state change
    socketio.emit("gamestate_update", state, namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, namespace="/player", to=game_id)


def setup_to_live(game_id: str, preset) -> None:
    if get_state(game_id) != State.SETUP:
        return

    with open(os.path.join(current_app.instance_path, "presets.json"), "r") as f:
        data = json.load(f).get(preset)

    if data is None:
        return

    game_setup = setup.GameSetup(
        game_id, os.path.join(current_app.instance_path, "presets", data["file"])
    )

    # Apply settings to Redis and notify clients on SocketIO
    game_setup.apply()

    set_state(game_id, State.LIVE)

    game_setup.start_clock()


def live_to_settlement(game_id):
    if get_state(game_id) != State.LIVE:
        return
    set_state(game_id, State.SETTLEMENT)


def settlement_to_results(game_id, true_prices):
    if get_state(game_id) != State.SETTLEMENT:
        return

    set_state(game_id, State.RESULTS)
