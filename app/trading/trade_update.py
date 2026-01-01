import json
from collections import defaultdict

from ..services import *


class TradeUpdate:
    def __init__(self, game_id, security):
        self.game_id = game_id
        self.security = security
        self.orderbook_key = f"game:{game_id}:security:{security}:orderbook"

        # Map of trader ids to map of security to quantity change
        self.inventory_updates = defaultdict(lambda: defaultdict(int))

        # Map of trader ids to order ids to (qty_change, new quantity)
        self.updated_orders = defaultdict(lambda: defaultdict(tuple))

        # Map of trader id to list of new orders to add
        self.new_orders = defaultdict(list)

        # Map of trader id to list of order IDs to delete
        self.deleted_orders = defaultdict(list)

        self.__cum_orderbook_change = defaultdict(int)  # price to cumulative qty change
        self.__cum_order_update = defaultdict(dict)  # trader id to cumulative changes

    def apply_inventory(self):
        for trader_id, inv in self.inventory_updates.items():
            inventory_new_vals = defaultdict(int)

            for sec_id, qty_change in inv.items():
                inventory_new_vals[sec_id] = extract(
                    r.hincrby(
                        f"user:{trader_id}:inventory",
                        sec_id,
                        qty_change,
                    )
                )

            trader_sid = r.hget(f"user:{trader_id}", "sid")
            socketio.emit(
                "inventory_update",
                inventory_new_vals,
                namespace="/player",
                to=trader_sid,
            )

    def apply_delete_orders(self):
        for trader_id, order_ids in self.deleted_orders.items():
            for order_id in order_ids:
                order_key = f"game:{self.game_id}:order:{order_id}"
                order = extract(r.hgetall(order_key))

                mult = 1 if order["side"] == "bids" else -1
                self.__cum_orderbook_change[order["price"]] -= (
                    int(order["quantity"]) * mult
                )

                counterparty_orders_key = f"user:{order['issuer_id']}:orders"
                orderside_key = f"{self.orderbook_key}:{order['side']}"

                r.srem(counterparty_orders_key, order_id)
                r.zrem(orderside_key, order_id)
                r.delete(order_key)
            self.__cum_order_update[trader_id]["deleted"] = order_ids

    def apply_modify_orders(self):
        for trader_id, orders in self.updated_orders.items():
            for order_id, (qty_change, new_qty) in orders.items():
                order_key = f"game:{self.game_id}:order:{order_id}"
                order = extract(r.hgetall(order_key))

                r.hset(f"game:{self.game_id}:order:{order_id}", "quantity", new_qty)

                mult = 1 if order["side"] == "bids" else -1
                self.__cum_orderbook_change[order["price"]] += qty_change * mult

            self.__cum_order_update[trader_id]["modified"] = orders

    def apply_new_orders(self):
        for trader_id, orders in self.new_orders.items():
            self.__cum_order_update[trader_id]["new"] = {}
            for order in orders:
                order_count = int(extract(r.incr(f"game:{self.game_id}:order_count")))
                order_id = "9" * 10 * (order_count // (10**10)) + str(
                    order_count % (10**10)
                ).rjust(10, "0")

                order_key = f"game:{self.game_id}:order:{order_id}"
                orderbook_key = (
                    f"game:{self.game_id}:security:{self.security}:orderbook"
                )
                orderside_key = f"{orderbook_key}:{order['side']}"
                orderbook_price = (
                    -order["price"] if order["side"] == "bids" else order["price"]
                )

                r.sadd(f"user:{trader_id}:orders", order_id)
                r.zadd(orderside_key, {order_id: orderbook_price})
                r.hset(order_key, mapping=order)

                mult = 1 if order["side"] == "bids" else -1
                self.__cum_orderbook_change[order["price"]] += (
                    int(order["quantity"]) * mult
                )

                self.__cum_order_update[trader_id]["new"][order_id] = order

    def apply(self):
        self.apply_new_orders()
        self.apply_modify_orders()
        self.apply_delete_orders()

        # Emit order updates to traders
        for trader_id, updates in self.__cum_order_update.items():
            trader_sid = r.hget(f"user:{trader_id}", "sid")
            socketio.emit(
                "order_update",
                updates,
                namespace="/player",
                to=trader_sid,
            )

        # Update orderbook
        orderbook_new_vals = defaultdict(int)
        for price, qty_change in self.__cum_orderbook_change.items():
            orderbook_key = f"game:{self.game_id}:security:{self.security}:orderbook"
            orderbook_new_vals[price] = extract(
                r.hincrby(orderbook_key, str(price), qty_change)
            )

        r.rpush(
            f"game:{self.game_id}:security:{self.security}:orderbook:updates",
            json.dumps(orderbook_new_vals),
        )
