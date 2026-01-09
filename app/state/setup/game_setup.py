import json, os
import numpy as np

from app.services import *
from app.bots.bot_manager import BotManager

from app.state import states
from app.state.live import margin, positions, prices
from app.communication import tick_flush


class GameSetup:
    def __init__(self, game_id, json_config_path: str):
        with open(json_config_path, "r") as f:
            config = json.load(f)

        self.game_id = game_id

        self.game_ticks = config.get("game_ticks", 100)
        self.tick_length = config.get("tick_length", 1)
        self.initial_cash = config.get("initial_cash", 100000)
        self.securities = config.get("securities", {})
        self.bot_manager = BotManager(game_id, config.get("bots", []))

    def apply(self):
        self.apply_redis()
        self.apply_socketio()

    def apply_redis(self):
        with r.lock("everything"):
            for sec_id, security in self.securities.items():
                r.sadd(f"game:{self.game_id}:securities", sec_id)
                r.hset(f"game:{self.game_id}:security:{sec_id}", mapping=security)

            r.hset(f"game:{self.game_id}", "game_ticks", self.game_ticks)
            r.hset(f"game:{self.game_id}", "tick_length", self.tick_length)
            r.hset(f"game:{self.game_id}", "initial_cash", self.initial_cash)

    def apply_socketio(self):
        socketio.emit(
            "securities_update", self.securities, namespace="/admin", to=self.game_id
        )
        socketio.emit(
            "securities_update", self.securities, namespace="/player", to=self.game_id
        )

    def start_clock(self):
        def tick_jobs():
            cur_tick = 0

            while states.get_state(self.game_id) == states.State.LIVE:
                if cur_tick >= self.game_ticks:
                    states.live_to_settlement(self.game_id)

                # 1. Run bots
                self.bot_manager.run_bots(cur_tick)

                # 2. Update prices
                prices.update_all_prices(self.game_id)

                # 3. Mark positions
                positions.mark_all_positions(self.game_id)

                # 4. Check margin calls / liquidations
                margin.check_margin(self.game_id)

                # 5. Flush orderbook updates to clients
                tick_flush.flush(self.game_id, self.securities)

                socketio.sleep(self.tick_length)
                cur_tick += 1

        socketio.start_background_task(tick_jobs)
