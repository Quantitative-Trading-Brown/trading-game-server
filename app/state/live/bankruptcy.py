from app.services import *
from app.exchange import cancellation
from app.communication import snapshot


def handle_bankruptcy(game_id, player_id):
    allowed_bankruptcies = int(
        extract(r.hget(f"game:{game_id}", "allowed_bankruptcies"))
    )
    bankruptcies = int(extract(r.hincrby(f"player:{player_id}", "bankruptcies")))

    r.set(f"player:{player_id}:inventory:cash", r.hget(f"game:{game_id}","initial_cash"))
    r.set(f"player:{player_id}:inventory:position_value", "0")
    r.set(f"player:{player_id}:inventory:margin", "0")
    r.delete(f"player:{player_id}:inventory")
    cancellation.cancel_all_orders(game_id, player_id)

    socketio.emit(
        "snapshot",
        snapshot.get_snapshot(game_id, player_id),
        namespace="/player",
        to=r.hget(f"player:{player_id}", "sid"),
    )

    socketio.emit(
        "bankruptcy",
        allowed_bankruptcies - bankruptcies,
        namespace="/player",
        to=r.hget(f"player:{player_id}", "sid"),
    )

    if bankruptcies >= allowed_bankruptcies:
        r.hset(f"player:{player_id}", "active", "0")
        r.srem(f"game:{game_id}:active_players", player_id)
        r.set(f"player:{player_id}:inventory:cash", "0")

        socketio.emit(
            "elimination",
            namespace="/player",
            to=r.hget(f"player:{player_id}", "sid"),
        )
