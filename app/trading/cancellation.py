import json
from collections import defaultdict

from ..services import *

def cancel_order(game_id: str, player_id: str, order_id: str) -> tuple[dict, dict]:
    orderbook_updates = defaultdict(int)
    order_updates = defaultdict(dict)

    user_orders_key = f"user:{player_id}:orders"
    order_key = f"game:{game_id}:order:{order_id}"

    order_details = extract(r.hgetall(order_key))

    order_security = order_details["security"]
    order_quantity = int(float(order_details["quantity"]))
    order_side = order_details["side"]
    order_price = order_details["price"]

    side_key = f"game:{game_id}:security:{order_security}:orderbook:{order_side}"
    update_quantity = -order_quantity if order_side == "bids" else order_quantity
    new_quantity = int(
        extract(
            r.hincrby(
                f"game:{game_id}:security:{order_security}:orderbook",
                order_price,
                update_quantity,
            )
        )
    )
    orderbook_updates[order_price] = new_quantity
    order_updates[player_id][order_id] = -1

    r.zrem(side_key, order_id)
    r.srem(user_orders_key, order_id)
    r.delete(order_key)

    r.rpush(
        f"game:{game_id}:security:{order_security}:orderbook:updates",
        json.dumps(orderbook_updates),
    )

    return order_security, order_updates


def cancel_all_orders(game_id: str, player_id: str) -> dict:
    orderbook_updates = defaultdict(dict)
    order_updates = defaultdict(dict)

    user_orders_key = f"user:{player_id}:orders"
    user_orders = extract(r.smembers(user_orders_key))

    for order_id in user_orders:
        order_key = f"game:{game_id}:order:{order_id}"

        order_details = extract(r.hgetall(order_key))

        order_security = order_details["security"]
        order_quantity = int(float(order_details["quantity"]))
        order_price = int(float(order_details["price"]))
        order_side = order_details["side"]

        orderside_key = (
            f"game:{game_id}:security:{order_security}:orderbook:{order_side}"
        )

        update_quantity = -order_quantity if order_side == "bids" else order_quantity
        new_quantity = int(
            extract(
                r.hincrby(
                    f"game:{game_id}:security:{order_security}:orderbook",
                    str(order_price),
                    update_quantity,
                )
            )
        )
        orderbook_updates[order_security][order_price] = new_quantity

        if not player_id.startswith("BOT"):
            order_updates[player_id][order_id] = -1

        r.srem(user_orders_key, order_id)
        r.zrem(orderside_key, order_id)
        r.delete(order_key)

    for security, security_orderbook_updates in orderbook_updates.items():
        r.rpush(
            f"game:{game_id}:security:{order_security}:orderbook:updates",
            json.dumps(security_orderbook_updates),
        )

    return order_updates
