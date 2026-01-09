import json
from collections import defaultdict

from ..services import *

from .executor import Executor


def process_limit_order(
    game_id: str,
    issuer_id: str,
    sec_id: str,
    order_side: str,
    price: float,
    quantity: int,
) -> None:
    executor = Executor(game_id, sec_id)

    # In Redis storage, prices for bids in the sorted set of the orderbook are negative to facilitate sorting
    # Prices in order details are always positive
    remaining_quantity = quantity

    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"  # Raw orderbook
    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"  # List of opposite orders sorted by price and recency

    orders_processed = 0
    while remaining_quantity > 0:
        best_in_orderbook = r.zrange(
            opposite_set_key, orders_processed, orders_processed, withscores=True
        )

        if (
            not best_in_orderbook
            or (order_side == "ask" and abs(best_in_orderbook[0][1]) < price)
            or (order_side == "bid" and abs(best_in_orderbook[0][1]) > price)
        ):
            break

        best_order_id = best_in_orderbook[0][0]

        trade_quantity, trade_price = process_trade(
            game_id,
            best_order_id,
            issuer_id,
            remaining_quantity,
            executor,
        )

        remaining_quantity -= trade_quantity
        orders_processed += 1

    # Put in new order if there is residual in the request
    if remaining_quantity > 0:
        executor.new_orders[issuer_id].append(
            {
                "security": sec_id,
                "side": orderbook_side,
                "price": price,
                "quantity": quantity,
                "issuer_id": issuer_id,
            }
        )

    executor.apply()


def process_market_order(
    game_id: str, issuer_id: str, sec_id: str, order_side: str, quantity: int
) -> None:
    executor = Executor(game_id, sec_id)

    remaining_quantity = quantity
    orderbook_key = f"game:{game_id}:security:{sec_id}:orderbook"

    orderbook_side = "bids" if order_side == "bid" else "asks"
    orderbook_opp = "asks" if order_side == "bid" else "bids"

    opposite_set_key = f"{orderbook_key}:{orderbook_opp}"

    # Market order continues consuming liquidity until empty
    orders_processed = 0
    while remaining_quantity > 0:
        best_price = r.zrange(
            opposite_set_key, orders_processed, orders_processed, withscores=True
        )

        # No liquidity available
        if not best_price:
            break

        best_order_id = best_price[0][0]
        trade_quantity, trade_price = process_trade(
            game_id,
            best_order_id,
            issuer_id,
            remaining_quantity,
            executor,
        )

        update_quantity = trade_quantity if order_side == "bid" else -trade_quantity
        remaining_quantity -= trade_quantity

        orders_processed += 1

    executor.apply()


def process_trade(
    game_id: str,
    order_id: str,
    initiator_id: str,
    requested_quantity: int,
    executor: Executor,
) -> tuple[int, float]:
    """
    Process a trade against an existing order in the orderbook.
    """
    order_key = f"game:{game_id}:order:{order_id}"
    order_details = extract(r.hgetall(order_key))

    issuer_id = order_details["issuer_id"]
    trade_price = int(float(order_details["price"]))

    avail_quantity = int(float(order_details["quantity"]))
    trade_quantity = min(requested_quantity, avail_quantity)

    # Update order if old order residual exists, else knock it out completely
    if avail_quantity > trade_quantity:
        executor.updated_orders[issuer_id][order_id] = (
            -trade_quantity,
            avail_quantity - trade_quantity,
        )
    else:
        executor.deleted_orders[issuer_id].append(order_id)

    buyer_id = initiator_id if order_details["side"] == "asks" else issuer_id
    seller_id = initiator_id if order_details["side"] == "bids" else issuer_id

    executor.cash_update[buyer_id] -= trade_price * trade_quantity
    executor.cash_update[seller_id] += trade_price * trade_quantity

    executor.inventory_update[buyer_id] += trade_quantity
    executor.inventory_update[seller_id] -= trade_quantity

    return trade_quantity, trade_price
