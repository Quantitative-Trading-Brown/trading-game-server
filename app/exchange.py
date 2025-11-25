from typing import Awaitable
from collections import defaultdict
import json

from .constants import r


def update_inventories(buyer_id, seller_id, sec_id, trade_quantity, trade_price):
    inventory_updates = defaultdict(dict)
    if not buyer_id.startswith("BOT"):
        inventory_updates[buyer_id][0] = float(
            r.hincrbyfloat(
                f"user:{buyer_id}:inventory",
                "0",
                -trade_price * trade_quantity,
            )
        )
        inventory_updates[buyer_id][sec_id] = int(
            r.hincrby(
                f"user:{buyer_id}:inventory",
                sec_id,
                trade_quantity,
            )
        )

    if not seller_id.startswith("BOT"):
        inventory_updates[seller_id][0] = float(
            r.hincrbyfloat(
                f"user:{seller_id}:inventory",
                "0",
                trade_price * trade_quantity,
            )
        )
        inventory_updates[seller_id][sec_id] = int(
            r.hincrby(
                f"user:{seller_id}:inventory",
                sec_id,
                -trade_quantity,
            )
        )
    return inventory_updates


def process_trade(
    game_id,
    initiator_id,
    order_id,
    orderbook_key,
    orderside_key,
    requested_quantity,
    orderbook_updates,
    order_updates,
    inventory_updates,
):
    order_key = f"game:{game_id}:order:{order_id}"
    order_details = r.hgetall(order_key)
    assert not isinstance(order_details, Awaitable)

    avail_quantity = int(float(order_details["quantity"]))
    counterparty_id = order_details["player_id"]
    counterparty_orders_key = f"user:{counterparty_id}:orders"

    trade_price = int(order_details["price"])
    trade_quantity = min(requested_quantity, avail_quantity)

    buyer_id = initiator_id if order_details["side"] == "asks" else counterparty_id
    seller_id = initiator_id if order_details["side"] == "bids" else counterparty_id

    # Update quantity in orderbook if old order residual exists, else knock it out completely
    if avail_quantity > trade_quantity:
        r.hset(order_key, "quantity", str(avail_quantity - trade_quantity))
        if not counterparty_id.startswith("BOT"):
            order_updates[counterparty_id][order_id] = r.hgetall(order_key)
    else:
        r.srem(counterparty_orders_key, order_id)
        r.zrem(orderside_key, order_id)
        r.delete(order_key)
        if not counterparty_id.startswith("BOT"):
            order_updates[counterparty_id][order_id] = -1

    orderbook_updates[trade_price] = int(
        r.hincrby(orderbook_key, str(trade_price), trade_quantity)
    )
    inventory_updates = inventory_updates | update_inventories(
        buyer_id, seller_id, order_details["security"], trade_quantity, trade_price
    )

    return trade_quantity, trade_price


def process_residual(
    game_id,
    player_id,
    sec_id,
    orderbook_side,
    price,
    quantity,
    orderbook_updates,
    order_updates,
):
    order_count = int(r.incr(f"game:{game_id}:order_count"))
    order_id = "9" * 10 * (order_count // (10**10)) + str(order_count % (10**10)).rjust(
        10, "0"
    )

    order_key = f"game:{game_id}:order:{order_id}"
    r.hset(
        order_key,
        mapping={
            "security": sec_id,
            "side": orderbook_side,
            "price": price,
            "quantity": quantity,
            "player_id": player_id,
        },
    )

    orderbook_price = -price if orderbook_side == "bids" else price
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook:{orderbook_side}"

    r.sadd(f"user:{player_id}:orders", order_id)
    r.zadd(orderbook_key, {order_id: orderbook_price})

    update_quantity = quantity if orderbook_side == "bids" else -quantity
    new_quantity = r.hincrby(orderbook_key, price, update_quantity)
    orderbook_updates[price] = new_quantity

    if not player_id.startswith("BOT"):
        order_updates[player_id][order_id] = r.hgetall(order_key)


def process_limit_order(game_id, player_id, sec_id, order_side, price, quantity):
    orderbook_updates = defaultdict(int)
    order_updates = defaultdict(dict)  # Maps user to dict of orders -> new quantities
    inventory_updates = defaultdict(dict)

    # In Redis storage, prices for bids in the sorted set are negative to facilitate sorting
    # Prices in order details are always positive
    remaining_quantity = quantity
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"
    user_orders_key = f"user:{player_id}:orders"

    order_opp = "ask" if order_side == "bid" else "bid"
    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"

    order_set_key = f"{orderbook_key}:{orderbook_side}"
    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"

    while remaining_quantity > 0:
        best_price = r.zrange(opposite_set_key, 0, 0, withscores=True)

        if (
            not best_price
            or (order_side == "ask" and abs(best_price[0][1]) < price)
            or (order_side == "bid" and abs(best_price[0][1]) > price)
        ):
            break

        best_order_id = best_price[0][0]

        trade_quantity, trade_price = process_trade(
            game_id,
            player_id,
            best_order_id,
            orderbook_key,
            opposite_set_key,
            remaining_quantity,
            orderbook_updates,
            order_updates,
            inventory_updates,
        )

        update_quantity = trade_quantity if order_side == "bid" else -trade_quantity
        remaining_quantity -= trade_quantity

    # Put in new order if there is residual in the new order
    if remaining_quantity > 0:
        process_residual(
            game_id,
            player_id,
            sec_id,
            orderbook_side,
            price,
            quantity,
            orderbook_updates,
            order_updates,
        )

    r.rpush(
        f"game:{game_id}:security:{sec_id}:orderbook:updates",
        json.dumps(orderbook_updates),
    )

    return inventory_updates, order_updates


def process_market_order(game_id, player_id, sec_id, order_side, quantity):
    orderbook_updates = defaultdict(int)
    order_updates = defaultdict(dict)
    inventory_updates = defaultdict(dict)

    remaining_quantity = quantity
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"
    user_orders_key = f"user:{player_id}:orders"

    order_opp = "ask" if order_side == "bid" else "bid"
    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"

    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"

    # Market order continues consuming liquidity until empty
    while remaining_quantity > 0:
        best_price = r.zrange(opposite_set_key, 0, 0, withscores=True)

        # No liquidity available
        if not best_price:
            break

        best_order_id = best_price[0][0]
        best_order_price = abs(best_price[0][1])  # stored as neg for bids

        trade_quantity, trade_price = (
            process_trade(
                game_id,
                player_id,
                best_order_id,
                orderbook_key,
                opposite_set_key,
                remaining_quantity,
                orderbook_updates,
                order_updates,
                inventory_updates,
            )
        )

        update_quantity = trade_quantity if order_side == "bid" else -trade_quantity
        orderbook_updates[trade_price] = int(
            r.hincrby(orderbook_key, str(trade_price), trade_quantity)
        )

        remaining_quantity -= trade_quantity

    r.rpush(
        f"game:{game_id}:security:{sec_id}:orderbook:updates",
        json.dumps(orderbook_updates),
    )

    return inventory_updates, order_updates


def cancel_order(game_id, player_id, order_id):
    orderbook_updates = defaultdict(int)
    order_updates = defaultdict(dict)

    user_orders_key = f"user:{player_id}:orders"
    order_key = f"game:{game_id}:order:{order_id}"

    order_details = r.hgetall(order_key)
    assert not isinstance(order_details, Awaitable)

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
    assert not isinstance(user_orders, Awaitable)

    for order_id in user_orders:
        order_key = f"game:{game_id}:order:{order_id}"

        order_details = r.hgetall(order_key)
        assert not isinstance(order_details, Awaitable)

        order_security = order_details["security"]
        order_quantity = int(float(order_details["quantity"]))
        order_price = int(float(order_details["price"]))
        order_side = order_details["side"]

        side_key = f"game:{game_id}:security:{order_security}:orderbook:{order_side}"

        update_quantity = -order_quantity if order_side == "bids" else order_quantity
        new_quantity = int(
            r.hincrby(
                f"game:{game_id}:security:{order_security}:orderbook",
                str(order_price),
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
