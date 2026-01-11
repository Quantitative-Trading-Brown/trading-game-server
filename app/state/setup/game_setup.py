import json, os
import numpy as np
import pandas as pd

from app.services import *
from app.bots.bot_manager import BotManager

from app.state import states
from app.state.live import margin, positions, prices
from app.communication import tick_flush, snapshot, broadcast


class GameSetup:
    def __init__(self, game_id, json_config_path: str):
        with open(json_config_path, "r") as f:
            config = json.load(f)

        self.game_id = game_id

        self.game_ticks = config.get("game_ticks", 100)
        self.tick_length = config.get("tick_length", 1)
        self.initial_cash = config.get("initial_cash", 100000)
        self.margin_call_ticks = config.get("margin_call_ticks", 3)
        self.allowed_bankruptcies = config.get("allowed_bankruptcies", 3)

        self.securities = config.get("securities", {})
        self.tick_data = pd.read_csv(
            os.path.join(current_app.instance_path, config.get("tick_data", ""))
        )
        self.bot_manager = BotManager(game_id, self.tick_data, config.get("bots", {}))

    def apply(self):
        self.apply_redis()
        self.apply_socketio()

    def apply_redis(self):
        with r.lock("everything"):
            for sec_id, security in self.securities.items():
                r.sadd(f"game:{self.game_id}:securities", sec_id)
                r.hset(f"game:{self.game_id}:security:{sec_id}", mapping=security)

            game_props = {
                "game_ticks": self.game_ticks,
                "tick_length": self.tick_length,
                "initial_cash": self.initial_cash,
                "allowed_bankruptcies": self.allowed_bankruptcies,
                "margin_call_ticks": self.margin_call_ticks,
            }
            r.hset(f"game:{self.game_id}", mapping=game_props)

            for player_id in extract(r.smembers(f"game:{self.game_id}:players")):
                r.set(
                    f"player:{player_id}:inventory:cash",
                    str(self.initial_cash),
                )

    def apply_socketio(self):
        socketio.emit(
            "snapshot",
            snapshot.get_snapshot(self.game_id),
            namespace="/admin",
            to=self.game_id,
        )
        for player_id in extract(r.smembers(f"game:{self.game_id}:players")):
            trader_sid = extract(r.hget(f"player:{player_id}", "sid"))
            if trader_sid is None:
                continue

            socketio.emit(
                "snapshot",
                snapshot.get_snapshot(self.game_id, player_id),
                namespace="/player",
                to=trader_sid,
            )

    def start_clock(self):
        def tick_jobs():
            cur_tick = 0

            while states.get_state(self.game_id) == states.State.LIVE:
                if cur_tick >= self.game_ticks:
                    states.live_to_settlement(self.game_id)

                with r.lock("everything"):
                    # 1. Run bots
                    self.bot_manager.run_bots(cur_tick)

                    # 2. Update prices
                    prices.update_all_prices(self.game_id)

                    # 3. Mark positions
                    positions.mark_all_positions(self.game_id)

                    # 4. Check margin calls / liquidations
                    margin.check_margin(self.game_id)

                    # 5. Flush orderbook updates to clients
                    tick_flush.flush(self.game_id)

                    # 6. Broadcast news to clients
                    news = self.tick_data["news"][cur_tick]
                    if isinstance(news, str) and news.strip() != "":
                        broadcast.news(self.game_id, news)

                socketio.sleep(self.tick_length)
                cur_tick += 1

        socketio.start_background_task(tick_jobs)
