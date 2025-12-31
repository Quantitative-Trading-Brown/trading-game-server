import json
from collections import defaultdict

from ..services import *


class TradeUpdate:
    def __init__(self, game_id, security):
        self.game_id = game_id
        self.security = security

        # Map of player ids to map of security to quantity change
        self.inventory_updates = defaultdict(dict)

        # Map of price levels to quantity change
        self.orderbook_updates = defaultdict(int)

        # Map of order ids to quantity change
        self.order_updates = defaultdict(int)

        # List of new orders to add
        self.new_orders = []

        # List of order IDs to delete
        self.deleted_orders = []

    def apply(self):
        self.apply_redis()
        self.apply_socketio()

    def apply_redis(self):
        # Update orderbook
        orderbook_new_vals = defaultdict(int)
        for price, qty_change in self.orderbook_updates.items():
            orderbook_key = f"game:{self.game_id}:security:{self.security}:orderbook"
            orderbook_new_vals[price] = extract(
                r.hincrby(orderbook_key, str(price), qty_change)
            )

        r.rpush(
            f"game:{self.game_id}:security:{self.security}:orderbook:updates",
            json.dumps(orderbook_new_vals),
        )

        # Update inventories
        for player_id, inv in self.inventory_updates.items():
            for sec_id, qty_change in inv.items():
                r.hincrby(
                    f"user:{player_id}:inventory",
                    sec_id,
                    qty_change,
                )

        # Update orders
        for order_id, qty_change in self.order_updates.items():
            order_key = f"game:{self.game_id}:order:{order_id}"
            r.hincrby(order_key, "quantity", qty_change)

        # New orders
        for order in self.new_orders:
            order_count = int(extract(r.incr(f"game:{self.game_id}:order_count")))
            order_id = "9" * 10 * (order_count // (10**10)) + str(
                order_count % (10**10)
            ).rjust(10, "0")

            order_key = f"game:{self.game_id}:order:{order_id}"
            orderbook_key = f"game:{self.game_id}:security:{self.security}:orderbook"
            orderside_key = f"{orderbook_key}:{order['side']}"

            r.sadd(f"user:{order['issuer_id']}:orders", order_id)

            orderbook_price = -price if order["side"] == "bids" else price
            r.zadd(orderside_key, {order_id: orderbook_price})

        # Deleted orders
        for order_id in self.deleted_orders:
            order_key = f"game:{self.game_id}:order:{order_id}"
            order = extract(r.hgetall(order_key))

            counterparty_orders_key = f"user:{order['player_id']}:orders"
            orderside_key = f"{orderbook_key}:{order['side']}"

            r.srem(counterparty_orders_key, order_id)
            r.zrem(orderside_key, order_id)
            r.delete(order_key)

    def apply_socketio(self):
        for trader_id, orders in self.order_updates.items():
            trader_sid = extract(r.hget(f"user:{trader_id}", "sid"))
            socketio.emit("orders", orders, namespace="/player", to=trader_sid)

        for trader_id, inv in self.inventory_updates.items():
            trader_sid = extract(r.hget(f"user:{trader_id}", "sid"))
            socketio.emit("inventory", inv, namespace="/player", to=trader_sid)
