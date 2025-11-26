import json
import time

from .bots import bots
from .utils import socketio, r
from .matching_engine import process_limit_order, cancel_order, cancel_all_orders

def start_bot(game_id):
    def run_bot():
        bot = bots["ts"]([100, 110, 120, 130, 140, 130, 120, 110], 3)
        while r.get(f"game:{game_id}:state") == "1":
            for quote in bot.place_orders(
                int(time.time()) - int(r.get(f"game:{game_id}:timestart")),
                r.hgetall(f"game:{game_id}:security:1:orderbook"),
            ):
                bot_order(game_id, 1, *quote)

            socketio.sleep(1)  # emits once per second

    socketio.start_background_task(run_bot)


def bot_order(game_id, security, order_side, price, quantity):
    exc_price = max(0, int(price))
    # Does not enforce quantity > 0

    trader_id = f"BOT_{game_id}"

    with r.lock("everything"):
        inventory_updates, order_updates = process_limit_order(
            game_id, trader_id, security, order_side, exc_price, quantity
        )

    for trader_id, orders in order_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("orders", orders, namespace="/player", to=trader_sid)

    for trader_id, inv in inventory_updates.items():
        trader_sid = r.hget(f"user:{trader_id}", "sid")
        socketio.emit("inventory", inv, namespace="/player", to=trader_sid)


def bot_cancel(game_id, order_id):
    trader_id = f"BOT_{game_id}"

    with r.lock("everything"):
        security, order_updates = cancel_order(game_id, trader_id, order_id)

    for trader_id in order_updates:
        trader_sid = r.hget("user:{trader_id}", "sid")
        socketio.emit(
            "orders", order_updates[trader_id], namespace="/player", to=trader_sid
        )


def bot_cancel_all(game_id):
    trader_id = f"BOT_{game_id}"

    with r.lock("everything"):
        order_updates = cancel_all_orders(game_id, trader_id)
