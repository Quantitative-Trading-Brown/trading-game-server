import json, os
import numpy as np
from flask import current_app

from ..services import *

from ..bots.bot_manager import BotManager


class GameSetup:
    def __init__(self, json_config_path: str):
        with open(json_config_path, "r") as f:
            config = json.load(f)

        self.game_ticks = config.get("game_ticks", 100)
        self.tick_length = config.get("tick_length", 1)
        self.securities = config.get("securities", {})
        self.bot_manager = BotManager(config.get("bots", []))

    def apply(self, game_id):
        self.apply_redis(game_id)
        self.apply_socketio(game_id)

    def apply_redis(self, game_id):
        with r.lock("everything"):
            for sec_id, security in self.securities.items():
                if sec_id == "USD":
                    raise Exception("Security ID 'USD' is reserved.")

                r.sadd(f"game:{game_id}:securities", sec_id)
                r.hset(f"game:{game_id}:security:{sec_id}", "name", security["name"])

            r.hset(f"game:{game_id}", "game_ticks", self.game_ticks)
            r.hset(f"game:{game_id}", "tick_length", self.tick_length)

    def apply_socketio(self, game_id):
        socketio.emit(
            "securities_update", self.securities, namespace="/admin", to=game_id
        )
        socketio.emit(
            "securities_update", self.securities, namespace="/player", to=game_id
        )
