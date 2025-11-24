from collections import defaultdict
import json

from .model import r
from .lsfr import next_order_id_64


def process_order(game_id, player_id, sec_id, order_side, price, quantity):
    """
    Processes a new order using Redis sorted sets for prices and hashes for order details.

    :param game_id          : The game_id
    :param player_id        : The id of the player making the new order
    :param sec_id           : The id of the security
    :param order_side       : The side of the new order ('bid' or 'ask')
    :param price            : New order price
    :param quantity         : New order quantity
    :return                 : A list of trades (buyer, seller, price, quantity).
    """
    # In the Redis storage, prices for bids in the sorted set are negative to facilitate sorting
    # Prices in order details are always positive
    orderbook_updates = defaultdict(int)
    order_updates = defaultdict(dict)  # Maps user to dict of orders -> new quantities
    inventory_updates = defaultdict(dict)


    remaining_quantity = quantity
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"
    user_orders_key = f"user:{player_id}:orders"

    order_opp = "ask" if order_side == "bid" else "bid"
    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"

    order_set_key = f"{orderbook_key}:{orderbook_side}"
    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"

    mrp = None

    while remaining_quantity > 0:
        best_price = r.zrange(opposite_set_key, 0, 0, withscores=True)

        if (
            not best_price
            or (order_side == "ask" and abs(best_price[0][1]) < price)
            or (order_side == "bid" and abs(best_price[0][1]) > price)
        ):
            break

        best_order_id = best_price[0][0]
        best_order_key = f"game:{game_id}:order:{best_order_id}"
        best_order_details = r.hgetall(best_order_key)

        avail_quantity = int(float(best_order_details["quantity"]))
        counterparty_id = best_order_details["player_id"]
        counterparty_orders_key = f"user:{counterparty_id}:orders"

        trade_price = int(best_order_details["price"])
        trade_quantity = min(remaining_quantity, avail_quantity)

        buyer_id = player_id if order_side == "bid" else counterparty_id
        seller_id = player_id if order_side == "ask" else counterparty_id

        # Calculate what the new orderbook volume is at this price level
        update_quantity = trade_quantity if order_side == "bid" else -trade_quantity
        new_quantity = int(r.hincrby(orderbook_key, trade_price, update_quantity))
        orderbook_updates[trade_price] = new_quantity

        # Update quantity in orderbook if old order residual exists, else knock it out completely
        if avail_quantity > trade_quantity:
            r.hset(best_order_key, "quantity", avail_quantity - trade_quantity)
            if not counterparty_id.startswith("BOT"):
                order_updates[counterparty_id][best_order_id] = r.hgetall(
                    best_order_key
                )
        else:
            r.srem(counterparty_orders_key, best_order_id)
            r.zrem(opposite_set_key, best_order_id)
            r.delete(best_order_key)
            if not counterparty_id.startswith("BOT"):
                order_updates[counterparty_id][best_order_id] = -1

        # Update users' positions

        if not buyer_id.startswith("BOT"):
            # Buyer -Cash
            new_quantity = float(
                r.hincrbyfloat(
                    f"user:{buyer_id}:inventory",
                    0,
                    -trade_price * trade_quantity,
                )
            )
            inventory_updates[buyer_id][0] = new_quantity

            # Buyer +Security
            new_quantity = int(
                r.hincrby(f"user:{buyer_id}:inventory", sec_id, trade_quantity)
            )
            inventory_updates[buyer_id][sec_id] = new_quantity

        if not seller_id.startswith("BOT"):
            # Seller +Cash
            new_quantity = float(
                r.hincrbyfloat(
                    f"user:{seller_id}:inventory",
                    0,
                    trade_price * trade_quantity,
                )
            )
            inventory_updates[seller_id][0] = new_quantity

            # Seller -Security
            new_quantity = int(
                r.hincrby(f"user:{seller_id}:inventory", sec_id, -trade_quantity)
            )
            inventory_updates[seller_id][sec_id] = new_quantity

        remaining_quantity -= trade_quantity
        mrp = trade_price

    # Put in new order if there is residual in the new order
    if remaining_quantity > 0:
        order_count = int(r.incr(f"{orderbook_key}:order_count"))
        order_id = "9" * 10 * (order_count // (10**10)) + str(
            order_count % (10**10)
        ).rjust(10, "0")

        order_key = f"game:{game_id}:order:{order_id}"
        r.hset(
            order_key,
            mapping={
                "security": sec_id,
                "side": orderbook_side,
                "price": price,
                "quantity": remaining_quantity,
                "player_id": player_id,
            },
        )

        orderbook_price = -price if order_side == "bid" else price

        r.sadd(user_orders_key, order_id)
        r.zadd(order_set_key, {order_id: orderbook_price})

        update_quantity = (
            remaining_quantity if order_side == "bid" else -remaining_quantity
        )
        new_quantity = r.hincrby(orderbook_key, price, update_quantity)
        orderbook_updates[price] = new_quantity

        if not player_id.startswith("BOT"):
            order_updates[player_id][order_id] = r.hgetall(order_key)

    r.rpush(
        f"game:{game_id}:security:{sec_id}:orderbook:updates",
        json.dumps(orderbook_updates),
    )

    return inventory_updates, order_updates, mrp


def cancel_order(game_id, player_id, order_id):
    orderbook_updates = defaultdict(int)
    order_updates = defaultdict(dict)

    user_orders_key = f"user:{player_id}:orders"
    order_key = f"game:{game_id}:order:{order_id}"

    order_details = r.hgetall(order_key)

    order_security = order_details["security"]
    order_quantity = int(float(order_details["quantity"]))
    order_side = order_details["side"]
    order_price = order_details["price"]

    side_key = f"game:{game_id}:security:{order_security}:orderbook:{order_side}"
    update_quantity = -order_quantity if order_side == "bids" else order_quantity
    new_quantity = int(
        r.hincrby(
            f"game:{game_id}:security:{order_security}:orderbook",
            order_price,
            update_quantity,
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


def cancel_all_orders(game_id, player_id):
    orderbook_updates = defaultdict(dict)
    order_updates = defaultdict(dict)

    user_orders_key = f"user:{player_id}:orders"
    user_orders = r.smembers(user_orders_key)

    for order_id in user_orders:
        order_key = f"game:{game_id}:order:{order_id}"

        order_details = r.hgetall(order_key)
        order_security = order_details["security"]
        order_quantity = int(float(order_details["quantity"]))
        order_price = int(float(order_details["price"]))
        order_side = order_details["side"]

        side_key = f"game:{game_id}:security:{order_security}:orderbook:{order_side}"

        update_quantity = -order_quantity if order_side == "bids" else order_quantity
        new_quantity = int(
            r.hincrby(
                f"game:{game_id}:security:{order_security}:orderbook",
                order_price,
                update_quantity,
            )
        )
        orderbook_updates[order_security][order_price] = new_quantity

        if not player_id.startswith("BOT"):
            order_updates[player_id][order_id] = -1

        r.srem(user_orders_key, order_id)
        r.zrem(side_key, order_id)
        r.delete(order_key)

    for security, security_orderbook_updates in orderbook_updates.items():
        r.rpush(
            f"game:{game_id}:security:{order_security}:orderbook:updates",
            json.dumps(security_orderbook_updates),
        )

    return order_updates
