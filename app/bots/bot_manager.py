import time, os
import numpy as np

from collections import defaultdict
from flask import current_app
import pandas as pd

from app.services import *
from app.exchange import entry, cancellation

from .templates import bot_templates


class BotManager:
    def __init__(
        self, game_id: str, tick_data: pd.DataFrame, bot_configs: dict[str, Any]
    ):
        ts_path = os.path.join(current_app.instance_path, "")
        self.active_bots = {}
        self.game_id = game_id

        for name, config in bot_configs.items():
            settings = config.get("settings", {})
            new_bot = bot_templates[config["type"]](tick_data, settings)

            self.active_bots[name] = (config["security"], new_bot)

    def run_bots(self, cur_tick):
        if cur_tick % 5 != 0:
            return
        self.bot_cancel_all()
        for name, (security, bot) in self.active_bots.items():
            for quote in bot.place_orders(
                cur_tick,
                r.hgetall(f"game:{self.game_id}:security:{security}:orderbook"),
            ):
                self.bot_order(security, *quote)

    def bot_order(self, security, order_side, price, quantity):
        trader_id = f"_bot_{self.game_id}"

        entry.process_limit_order(
            self.game_id, trader_id, security, order_side, price, quantity
        )

    def bot_cancel(self, order_id):
        trader_id = f"_bot_{self.game_id}"

        cancellation.cancel_order(self.game_id, trader_id, order_id)

    def bot_cancel_all(self):
        trader_id = f"_bot_{self.game_id}"

        cancellation.cancel_all_orders(self.game_id, trader_id)
