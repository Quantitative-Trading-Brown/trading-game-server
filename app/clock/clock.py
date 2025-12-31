import json, time

from ..control import state, setup
from ..services import *

from .flush_orderbook import flush_orderbook

def clock_start(game_id: str, game_setup: setup.GameSetup):
    def tick_jobs():
        cur_tick = 0

        while r.get(f"game:{game_id}:state") == "1":
            if cur_tick >= game_setup.game_ticks:
                state.set_state(game_id, 2)

            # 1. Run bots
            game_setup.bot_manager.run_bots(game_id, cur_tick)

            # 2. Flush orderbook updates to clients
            flush_orderbook(game_id)

            socketio.sleep(game_setup.tick_length)
            cur_tick += 1

    socketio.start_background_task(tick_jobs)
