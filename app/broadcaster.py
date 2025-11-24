from .model import socketio, r
import json


def start_update_flusher(game_id):
    def flusher():
        while True:
            if r.get(f"game:{game_id}:state") != "1":
                break

            flush_buffer_for_game(game_id)
            socketio.sleep(1)  # emits once per second

    socketio.start_background_task(flusher)


def flush_buffer_for_game(game_id):
    with r.lock("everything"):
        for security in r.smembers(f"game:{game_id}:securities"):
            ob_key = f"game:{game_id}:security:{security}:orderbook:updates"
            orderbook_items = r.lrange(ob_key, 0, -1)

            if orderbook_items:
                orderbook_update_queue = [json.loads(x) for x in orderbook_items]
                combined = {k: v for d in orderbook_update_queue for k, v in d.items()}
                r.delete(ob_key)

                # Emit combined orderbook updates
                socketio.emit("orderbook", (security, combined), namespace="/player", to=game_id)
                socketio.emit("orderbook", (security, combined), namespace="/admin", to=game_id)
