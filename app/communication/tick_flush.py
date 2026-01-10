import json

from app.services import *


def flush(game_id: str, securities: dict) -> None:
    # Should flush tick-based updates to the player

    # Combine and emit orderbook/price updates
    with r.lock("everything"):
        total_update = {}
        for sec_id in securities:
            ob_key = f"game:{game_id}:security:{sec_id}:orderbook:updates"
            orderbook_items = extract(r.lrange(ob_key, 0, -1))

            orderbook_update_queue = [json.loads(x) for x in orderbook_items]
            combined = {
                float(price): qty
                for d in orderbook_update_queue
                for price, qty in d.items()
            }
            total_update[sec_id] = combined
            r.delete(ob_key)

        prices = r.hgetall(f"game:{game_id}:securities:prices")

        # Emit combined orderbook updates
        socketio.emit("orderbook", total_update, namespace="/player", to=game_id)
        socketio.emit("orderbook", total_update, namespace="/admin", to=game_id)

        socketio.emit("prices", prices, namespace="/player", to=game_id)
        socketio.emit("prices", prices, namespace="/admin", to=game_id)

    # Emit inventory equity updates
    with r.lock("everything"):
        players = extract(r.smembers(f"game:{game_id}:players"))

        for player_id in players:
            trader_sid = extract(r.hget(f"player:{player_id}", "sid"))
            if trader_sid is None:
                continue

            position_value = extract(
                r.get(f"player:{player_id}:inventory:position_value")
            )
            margin = extract(r.get(f"player:{player_id}:inventory:margin"))


            socketio.emit(
                "inventory",
                {"position_value": position_value, "margin": margin},
                namespace="/player",
                to=trader_sid,
            )
