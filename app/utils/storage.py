from typing import Awaitable, Any
import valkey
import json

from .socketio import socketio

r = valkey.Valkey(host="localhost", port=6379, db=0, decode_responses=True)

def extract(value: Any) -> Any:
    if value is None:
        raise RuntimeError("No value found.")
    if isinstance(value, Awaitable):
        raise RuntimeError("Async operation not supported here.")
    return value

def set_state(game_id, state):
    # Update in Redis backend
    r.set(f"game:{game_id}:state", state)

    # Notify all clients about the state change
    socketio.emit("gamestate_update", state, namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, namespace="/player", to=game_id)

def generate_rankings(game_id):
    # Calculate player scores based on true prices and inventories
    true_prices = extract(r.hgetall(f"game:{game_id}:true_prices"))
    players = extract(r.zrangebyscore(f"game:{game_id}:users", 0, 0))

    for player_id in players:
        player_inv = extract(r.hgetall(f"user:{player_id}:inventory"))

        score = 0
        for sec_id in player_inv:
            score += float(true_prices[sec_id]) * float(player_inv[sec_id])
        r.zadd(f"game:{game_id}:users", {str(player_id): round(score, 2)})
    return r.zrevrange(f"game:{game_id}:users", 0, -1, withscores=True)

def flush_orderbook(game_id):
    with r.lock("everything"):
        securities = extract(r.smembers(f"game:{game_id}:securities"))

        total_update = {}
        for security in securities:
            ob_key = f"game:{game_id}:security:{security}:orderbook:updates"
            orderbook_items = extract(r.lrange(ob_key, 0, -1))

            if orderbook_items:
                orderbook_update_queue = [json.loads(x) for x in orderbook_items]
                combined = {k: v for d in orderbook_update_queue for k, v in d.items()}
                total_update[security] = combined
                r.delete(ob_key)

        # Emit combined orderbook updates
        socketio.emit(
            "orderbook", total_update, namespace="/player", to=game_id
        )
        socketio.emit(
            "orderbook", total_update, namespace="/admin", to=game_id
        )
