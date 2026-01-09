import json
from collections import defaultdict

from app.services import *
from app.state.live import positions


class Executor:
    def __init__(self, game_id, security):
        self.game_id = game_id
        self.security = security
        self.orderbook_key = f"game:{game_id}:security:{security}:orderbook"

        self.cash_update = defaultdict(float)  # trader id to cash change

        # Map of trader ids to map of security to quantity change
        self.inventory_update = defaultdict(int)

        # Map of trader ids to order ids to (qty_change, new quantity)
        self.updated_orders = defaultdict(lambda: defaultdict(tuple))

        # Map of trader id to list of new orders to add
        self.new_orders = defaultdict(list)

        # Map of trader id to list of order IDs to delete
        self.deleted_orders = defaultdict(list)

        self.__cum_orderbook_change = defaultdict(int)  # price to cumulative qty change
        self.__cum_order_update = defaultdict(dict)  # trader id to cumulative changes

    def calc_deleted_orders(self):
        for trader_id, order_ids in self.deleted_orders.items():
            for order_id in order_ids:
                order_key = f"game:{self.game_id}:order:{order_id}"
                order = extract(r.hgetall(order_key))

                mult = 1 if order["side"] == "bids" else -1
                self.__cum_orderbook_change[order["price"]] -= (
                    int(order["quantity"]) * mult
                )

                counterparty_orders_key = f"player:{order['issuer_id']}:orders"
                orderside_key = f"{self.orderbook_key}:{order['side']}"

                r.srem(counterparty_orders_key, order_id)
                r.zrem(orderside_key, order_id)
                r.delete(order_key)
            self.__cum_order_update[trader_id]["deleted"] = order_ids

    def calc_modified_orders(self):
        for trader_id, orders in self.updated_orders.items():
            for order_id, (qty_change, new_qty) in orders.items():
                order_key = f"game:{self.game_id}:order:{order_id}"
                order = extract(r.hgetall(order_key))

                r.hset(f"game:{self.game_id}:order:{order_id}", "quantity", new_qty)

                mult = 1 if order["side"] == "bids" else -1
                self.__cum_orderbook_change[order["price"]] += qty_change * mult

            self.__cum_order_update[trader_id]["modified"] = orders

    def calc_new_orders(self):
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

                r.sadd(f"player:{trader_id}:orders", order_id)
                r.zadd(orderside_key, {order_id: orderbook_price})
                r.hset(order_key, mapping=order)

                mult = 1 if order["side"] == "bids" else -1
                self.__cum_orderbook_change[order["price"]] += (
                    int(order["quantity"]) * mult
                )

                self.__cum_order_update[trader_id]["new"][order_id] = order

    def apply_orders(self):
        self.calc_new_orders()
        self.calc_modified_orders()
        self.calc_deleted_orders()

        # Emit order updates to traders
        for trader_id, updates in self.__cum_order_update.items():
            if trader_id.startswith("_bot_"):
                continue
            trader_sid = r.hget(f"player:{trader_id}", "sid")
            socketio.emit(
                "order_update",
                updates,
                namespace="/player",
                to=trader_sid,
            )

    def apply_orderbook(self):
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

    def apply_inventory(self):
        for trader_id, qty_change in self.inventory_update.items():
            if trader_id.startswith("_bot_"):  # Ignore bot inventory
                continue

            cash = extract(
                r.incrbyfloat(
                    f"player:{trader_id}:inventory:cash", self.cash_update[trader_id]
                )
            )

            amount = extract(
                r.hincrby(
                    f"player:{trader_id}:inventory",
                    self.security,
                    qty_change,
                )
            )

            positions.mark_player_positions(
                self.game_id,
                trader_id,
                prices={
                    self.security: extract(
                        r.hget(f"game:{self.game_id}:securities:prices", self.security)
                    )
                },
            )

            position_value = extract(
                r.get(f"player:{trader_id}:inventory:position_value")
            )

            margin = extract(
                r.get(f"player:{trader_id}:inventory:margin")
            )

            trader_sid = r.hget(f"player:{trader_id}", "sid")
            socketio.emit(
                "inventory",
                {
                    "cash": cash,
                    "position_value": position_value,
                    "margin": margin,
                    "securities": {self.security: amount},
                },
                namespace="/player",
                to=trader_sid,
            )

    def apply(self):
        self.apply_orders()
        self.apply_orderbook()
        self.apply_inventory()
