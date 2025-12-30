import time, os
from collections import defaultdict
import numpy as np
from flask import current_app

from .templates import *
from ..utils.storage import r
from ..utils.socketio import socketio

from ..matching_engine import matching_engine as me


class BotManager:
    def __init__(self, bot_config):
        ts_path = os.path.join(current_app.instance_path, "timeseries")
        self.active_bots = defaultdict(list)

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

    def run_bots(self, game_id, cur_tick):
        for security, bots in self.active_bots.items():
            for bot in bots:
                for quote in bot.place_orders(
                    cur_tick,
                    r.hgetall(f"game:{game_id}:security:{security}:orderbook"),
                ):
                    self.bot_order(game_id, security, *quote)

    def bot_order(self, game_id, security, order_side, price, quantity):
        exc_price = max(0, int(price))
        exc_qty = max(1, int(quantity))

        trader_id = f"BOT_{game_id}"

        with r.lock("everything"):
            inventory_updates, order_updates = me.process_limit_order(
                game_id, trader_id, security, order_side, exc_price, exc_qty
            )

        for trader_id, orders in order_updates.items():
            trader_sid = r.hget(f"user:{trader_id}", "sid")
            socketio.emit("orders", orders, namespace="/player", to=trader_sid)

        for trader_id, inv in inventory_updates.items():
            trader_sid = r.hget(f"user:{trader_id}", "sid")
            socketio.emit("inventory", inv, namespace="/player", to=trader_sid)

    def bot_cancel(self, game_id, order_id):
        trader_id = f"BOT_{game_id}"

        with r.lock("everything"):
            security, order_updates = me.cancel_order(game_id, trader_id, order_id)

        for trader_id in order_updates:
            trader_sid = r.hget("user:{trader_id}", "sid")
            socketio.emit(
                "orders", order_updates[trader_id], namespace="/player", to=trader_sid
            )

    def bot_cancel_all(self, game_id):
        trader_id = f"BOT_{game_id}"

        with r.lock("everything"):
            order_updates = me.cancel_all_orders(game_id, trader_id)
