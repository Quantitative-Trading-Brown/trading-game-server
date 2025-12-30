import json, time
from typing import Awaitable

from .utils.socketio import socketio
from .utils.storage import r, extract
from .utils import storage

from .setup import GameSetup

def clock_start(game_id, setup: GameSetup):
    def tick_jobs():
        cur_tick = 0

        while r.get(f"game:{game_id}:state") == "1":
            setup.bot_manager.run_bots(game_id, cur_tick)
            storage.flush_orderbook(game_id)

            socketio.sleep(setup.tick_length)
            cur_tick += 1

            if cur_tick >= setup.game_ticks:
                storage.set_state(game_id, 2)

    socketio.start_background_task(tick_jobs)


