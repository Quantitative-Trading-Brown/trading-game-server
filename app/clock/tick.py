import json, time

from ..control import state, setup
from ..services import *

def clock_start(game_id: str, game_setup: setup.GameSetup):
    def tick_jobs():
        cur_tick = 0

        while r.get(f"game:{game_id}:state") == "1":
            if cur_tick >= game_setup.game_ticks:
                state.set_state(game_id, 2)

            # 1. Run bots
            game_setup.bot_manager.run_bots(game_id, cur_tick)

            # 2. Flush orderbook updates to clients
            flush_orderbook(game_id, game_setup.securities)

            socketio.sleep(game_setup.tick_length)
            cur_tick += 1

    socketio.start_background_task(tick_jobs)

def flush_orderbook(game_id: str, securities: dict) -> None:
    with r.lock("everything"):
        total_update = {}
        for sec_id in securities:
            ob_key = f"game:{game_id}:security:{sec_id}:orderbook:updates"
            orderbook_items = extract(r.lrange(ob_key, 0, -1))

            orderbook_update_queue = [json.loads(x) for x in orderbook_items]
            combined = {k: v for d in orderbook_update_queue for k, v in d.items()}
            total_update[sec_id] = combined
            r.delete(ob_key)

        # Emit combined orderbook updates
        socketio.emit("orderbook", total_update, namespace="/player", to=game_id)
        socketio.emit("orderbook", total_update, namespace="/admin", to=game_id)
