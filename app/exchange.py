from collections import defaultdict

from .model import Trade, r


def process_order(game_id, player_id, sec_id, order_type, price, amount):
    """
    Processes a new order using Redis sorted sets for prices and hashes for order details.

    :param game_id          : The game_id
    :param player_id        : The id of the player making the new order
    :param sec_id           : The id of the security
    :param order_type       : The type of the new order ('buy' or 'sell')
    :param price            : New order price
    :param amount           : New order amount
    :return                 : A list of trades (buyer, seller, price, amount).
    """
    # In the Redis storage, prices for bids in the sorted set are negative to facilitate sorting
    # Prices in order details are always positive
    orderbook_updates = defaultdict(int)
    inventory_updates = defaultdict(dict)

    remaining_amount = amount
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"
    user_orders_key = f"user:{player_id}:security:{sec_id}:orders"

    order_set_key = f"{orderbook_key}:{'bids' if order_type == 'BUY' else 'asks'}"
    opposite_set_key = f"{orderbook_key}:{'asks' if order_type == 'BUY' else 'bids'}"

    security_scale = float(r.hget(f"game:{game_id}:security:{sec_id}", "scale"))

    mrp = None

    while remaining_amount > 0:
        best_price = r.zrange(opposite_set_key, 0, 0, withscores=True)

        if (
            not best_price
            or (order_type == "SELL" and abs(best_price[0][1]) < price)
            or (order_type == "BUY" and abs(best_price[0][1]) > price)
        ):
            break

        best_order_id = best_price[0][0]
        best_order_details = r.hgetall(best_order_id)

        avail_amount = int(float(best_order_details["amount"]))
        counterparty_id = int(best_order_details["player_id"])
        counterparty_orders_key = f"user:{counterparty_id}:security:{sec_id}:orders"

        trade_price = int(best_order_details["price"])
        trade_amount = min(remaining_amount, avail_amount)

        buyer_id = player_id if order_type == "BUY" else counterparty_id
        seller_id = player_id if order_type == "SELL" else counterparty_id

        # Create updates for the client
        update_amount = trade_amount if order_type == "BUY" else -trade_amount
        new_amount = int(r.hincrby(orderbook_key, trade_price, update_amount))
        orderbook_updates[trade_price] = new_amount

        # Update amount in orderbook if old order residual exists, else knock it out completely
        if avail_amount > trade_amount:
            r.hset(best_order_id, "amount", avail_amount - trade_amount)
        else:
            r.zrem(counterparty_orders_key, best_order_id)
            r.zrem(opposite_set_key, best_order_id)
            r.delete(best_order_id)

        # Update users' positions

        # Buyer -Cash
        new_amount = float(
            r.hincrbyfloat(
                f"user:{buyer_id}:inventory",
                0,
                -trade_price * trade_amount * security_scale,
            )
        )
        inventory_updates[buyer_id][0] = new_amount

        # Buyer +Security
        new_amount = int(r.hincrby(f"user:{buyer_id}:inventory", sec_id, trade_amount))
        inventory_updates[buyer_id][sec_id] = new_amount

        # Seller +Cash
        new_amount = float(
            r.hincrbyfloat(
                f"user:{seller_id}:inventory",
                0,
                trade_price * trade_amount * security_scale,
            )
        )
        inventory_updates[seller_id][0] = new_amount

        # Seller -Security
        new_amount = int(
            r.hincrby(f"user:{seller_id}:inventory", sec_id, -trade_amount)
        )
        inventory_updates[seller_id][sec_id] = new_amount

        remaining_amount -= trade_amount
        mrp = trade_price

    # Put in new order if there is residual in the new order
    if remaining_amount > 0:
        order_count = int(r.incr(f"{orderbook_key}:order_count"))
        order_id = "9" * 3 * (order_count // (10**3)) + str(
            order_count % (10**3)
        ).rjust(3, "0")

        order_key = f"{orderbook_key}:{order_id}"
        r.hset(
            order_key,
            mapping={
                "side": "bids" if order_type == "BUY" else "asks",
                "price": price,
                "amount": remaining_amount,
                "player_id": player_id,
            },
        )

        r.zadd(user_orders_key, {order_key: price})

        orderbook_price = -price if order_type == "BUY" else price
        r.zadd(order_set_key, {order_key: orderbook_price})

        update_amount = remaining_amount if order_type == "BUY" else -remaining_amount
        new_amount = r.hincrby(orderbook_key, price, update_amount)
        orderbook_updates[price] = new_amount

    return orderbook_updates, inventory_updates, mrp


def cancel_order(game_id, player_id, sec_id, price):
    orderbook_updates = defaultdict(int)

    user_orders_key = f"user:{player_id}:security:{sec_id}:orders"
    user_orders = r.zrangebyscore(user_orders_key, price, price)

    for order_id in user_orders:
        order_details = r.hgetall(order_id)
        order_amount = int(float(order_details["amount"]))

        order_side = order_details["side"]
        side_key = f"game:{game_id}:security:{sec_id}:orderbook:{order_side}"

        update_amount = -order_amount if order_side == "bids" else order_amount
        new_amount = int(
            r.hincrby(
                f"game:{game_id}:security:{sec_id}:orderbook", price, update_amount
            )
        )
        orderbook_updates[price] = new_amount

        r.zrem(side_key, order_id)
        r.zrem(user_orders_key, order_id)
        r.delete(order_id)
    return orderbook_updates


def cancel_all_orders(game_id, player_id, sec_id):
    orderbook_updates = defaultdict(int)

    user_orders_key = f"user:{player_id}:security:{sec_id}:orders"
    user_orders = r.zrange(user_orders_key, 0, -1)

    for order_id in user_orders:
        order_details = r.hgetall(order_id)
        order_amount = int(float(order_details["amount"]))
        order_price = int(float(order_details["price"]))

        order_side = order_details["side"]
        side_key = f"game:{game_id}:security:{sec_id}:orderbook:{order_side}"

        update_amount = -order_amount if order_side == "bids" else order_amount
        new_amount = int(
            r.hincrby(
                f"game:{game_id}:security:{sec_id}:orderbook",
                order_price,
                update_amount,
            )
        )
        orderbook_updates[order_price] = new_amount

        r.zrem(side_key, order_id)
        r.delete(order_id)

    r.delete(user_orders_key)

    return orderbook_updates
