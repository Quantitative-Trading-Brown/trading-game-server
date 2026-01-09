import time, os
import numpy as np

from collections import defaultdict
from flask import current_app

from app.services import *
from app.exchange import entry, cancellation

from .templates import *


class BotManager:
    def __init__(self, game_id, bot_config):
        ts_path = os.path.join(current_app.instance_path, "timeseries")
        self.active_bots = defaultdict(list)
        self.game_id = game_id

        for bot in bot_config:
            settings = bot.get("settings", {})

            match bot["type"]:
                case "custom":
                    series = np.genfromtxt(
                        os.path.join(ts_path, settings["series"]), delimiter=","
                    )

                    self.active_bots[bot["security"]].append(
                        TimeSeriesBot(series, settings["width"])
                    )
                    break
                case "flat":
                    self.active_bots[bot["security"]].append(
                        FlatBot(settings["price_level"], settings["width"])
                    )
                    break
                case "sinewave":
                    self.active_bots[bot["security"]].append(
                        SinewaveBot(
                            settings["base_price"],
                            settings["amplitude"],
                            settings["frequency"],
                        )
                    )
                    break

    def run_bots(self, cur_tick):
        self.bot_cancel_all()
        for security, bots in self.active_bots.items():
            for bot in bots:
                for quote in bot.place_orders(
                    cur_tick,
                    r.hgetall(f"game:{self.game_id}:security:{security}:orderbook"),
                ):
                    self.bot_order(security, *quote)

    def bot_order(self, security, order_side, price, quantity):
        trader_id = f"_bot_{self.game_id}"

        with r.lock("everything"):
            entry.process_limit_order(
                self.game_id, trader_id, security, order_side, price, quantity
            )

    def bot_cancel(self, order_id):
        trader_id = f"_bot_{self.game_id}"

        with r.lock("everything"):
            cancellation.cancel_order(self.game_id, trader_id, order_id)

    def bot_cancel_all(self):
        trader_id = f"_bot_{self.game_id}"

        with r.lock("everything"):
            cancellation.cancel_all_orders(self.game_id, trader_id)
