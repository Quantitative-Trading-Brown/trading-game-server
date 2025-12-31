import json


from ..services import *


def flush_orderbook(game_id: str) -> None:
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
        socketio.emit("orderbook", total_update, namespace="/player", to=game_id)
        socketio.emit("orderbook", total_update, namespace="/admin", to=game_id)
